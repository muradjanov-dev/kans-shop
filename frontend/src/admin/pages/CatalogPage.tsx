import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import type { AdminCategory, AdminProduct, ProductImage } from "@/admin/adminTypes";
import { getAdminApiErrorCode } from "@/admin/api";
import {
  createAdminCategory,
  createAdminProduct,
  deleteAdminCategoryImage,
  deleteAdminProductImage,
  getAdminCategories,
  getAdminProduct,
  invalidateAdminCatalog,
  updateAdminCategory,
  updateAdminProduct,
  updateAdminProductImage,
  uploadAdminCategoryImage,
  uploadAdminProductImage,
  useAdminCategories,
  useAdminProducts,
} from "@/admin/adminQueries";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import {
  AdminActionError,
  AdminEmptyState,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminAmount,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

interface ProductDraft {
  category_id: string;
  name_uz: string;
  name_ru: string;
  description_uz: string;
  description_ru: string;
  sku: string;
  barcode: string;
  price: string;
  old_price: string;
  stock_qty: string;
  unit: AdminProduct["unit"];
  min_order_qty: string;
  is_active: boolean;
  is_featured: boolean;
  sort_order: string;
  lot_url: string;
}

interface CategoryDraft {
  parent_id: string;
  name_uz: string;
  name_ru: string;
  description_uz: string;
  description_ru: string;
  sort_order: string;
  is_active: boolean;
}

interface ProductEditor {
  id: number | null;
  version: number;
  latestVersion: number | null;
  conflict: boolean;
  conflictRefreshed: boolean;
  draft: ProductDraft;
  images: ProductImage[];
}

interface CategoryEditor {
  id: number | null;
  version: number;
  latestVersion: number | null;
  conflict: boolean;
  conflictRefreshed: boolean;
  draft: CategoryDraft;
}

const unitOptions: AdminProduct["unit"][] = ["dona", "quti", "paket", "komplekt"];

export function CatalogPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const queryClient = useQueryClient();
  const categories = useAdminCategories();
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const products = useAdminProducts(categoryId);
  const [productEditor, setProductEditor] = useState<ProductEditor | null>(null);
  const [categoryEditor, setCategoryEditor] = useState<CategoryEditor | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [categoryPhoto, setCategoryPhoto] = useState<File | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (categoryId === null && categories.data?.length) setCategoryId(categories.data[0].id);
  }, [categories.data, categoryId]);

  const refreshCatalog = async () => invalidateAdminCatalog(queryClient);
  const saveProduct = useMutation({
    mutationFn: async () => {
      if (!productEditor) throw new Error("No product draft");
      const body = productBody(productEditor.draft, productEditor.id !== null);
      return productEditor.id === null
        ? createAdminProduct(body)
        : updateAdminProduct(productEditor.id, { ...body, expected_edit_version: productEditor.latestVersion ?? productEditor.version });
    },
    onSuccess: async (product) => {
      setProductEditor(null);
      setPhoto(null);
      setActionError(null);
      await refreshCatalog();
      if (categoryId === null) setCategoryId(product.category_id);
    },
    onError: (error) => {
      setActionError(error);
      if (getAdminApiErrorCode(error) === "ENTITY_CONFLICT") setProductEditor((current) => current ? { ...current, conflict: true, conflictRefreshed: false } : current);
    },
  });
  const saveCategory = useMutation({
    mutationFn: async () => {
      if (!categoryEditor) throw new Error("No category draft");
      const body = categoryBody(categoryEditor.draft, categoryEditor.id !== null);
      return categoryEditor.id === null
        ? createAdminCategory(body)
        : updateAdminCategory(categoryEditor.id, { ...body, expected_edit_version: categoryEditor.latestVersion ?? categoryEditor.version });
    },
    onSuccess: async (category) => {
      setCategoryEditor(null);
      setCategoryPhoto(null);
      setActionError(null);
      await refreshCatalog();
      setCategoryId(category.id);
    },
    onError: (error) => {
      setActionError(error);
      if (getAdminApiErrorCode(error) === "ENTITY_CONFLICT") setCategoryEditor((current) => current ? { ...current, conflict: true, conflictRefreshed: false } : current);
    },
  });
  const uploadProductPhoto = useMutation({
    mutationFn: () => productEditor?.id === null || !productEditor || !photo
      ? Promise.reject(new Error("Choose a saved product and photo"))
      : uploadAdminProductImage(productEditor.id, photo),
    onSuccess: async (product) => { setProductEditor((current) => current ? { ...current, images: product.images } : current); setPhoto(null); await refreshCatalog(); },
    onError: (error) => setActionError(error),
  });
  const updateImage = useMutation({
    mutationFn: ({ imageId, isMain, sortOrder }: { imageId: number; isMain: boolean; sortOrder: number }) => {
      if (!productEditor?.id) throw new Error("No saved product");
      return updateAdminProductImage(productEditor.id, imageId, { is_main: isMain, sort_order: sortOrder });
    },
    onSuccess: async (product) => { setProductEditor((current) => current ? { ...current, images: product.images } : current); await refreshCatalog(); },
    onError: (error) => setActionError(error),
  });
  const removeImage = useMutation({
    mutationFn: (imageId: number) => productEditor?.id ? deleteAdminProductImage(productEditor.id, imageId) : Promise.reject(new Error("No saved product")),
    onSuccess: async (product) => { setProductEditor((current) => current ? { ...current, images: product.images } : current); await refreshCatalog(); },
    onError: (error) => setActionError(error),
  });
  const uploadCategoryPhoto = useMutation({
    mutationFn: () => categoryEditor?.id === null || !categoryEditor || !categoryPhoto
      ? Promise.reject(new Error("Choose a saved category and photo"))
      : uploadAdminCategoryImage(categoryEditor.id, categoryPhoto),
    onSuccess: async () => { setCategoryPhoto(null); await refreshCatalog(); },
    onError: (error) => setActionError(error),
  });
  const removeCategoryPhoto = useMutation({
    mutationFn: () => categoryEditor?.id ? deleteAdminCategoryImage(categoryEditor.id) : Promise.reject(new Error("No saved category")),
    onSuccess: async (category) => {
      await refreshCatalog();
      setCategoryEditor((current) => current ? { ...current, version: category.edit_version, draft: { ...current.draft } } : current);
      setNotice(t("admin.catalog.category_image_removed"));
    },
    onError: (error) => setActionError(error),
  });

  function editProduct(product: AdminProduct) {
    setActionError(null);
    setNotice("");
    setProductEditor({ id: product.id, version: product.edit_version, latestVersion: null, conflict: false, conflictRefreshed: false, draft: productDraft(product), images: [...product.images] });
  }

  function editCategory(category: AdminCategory) {
    setActionError(null);
    setNotice("");
    setCategoryEditor({ id: category.id, version: category.edit_version, latestVersion: null, conflict: false, conflictRefreshed: false, draft: categoryDraft(category) });
  }

  async function refreshConflictRecord() {
    setActionError(null);
    if (productEditor?.id) {
      try {
        const latest = await getAdminProduct(productEditor.id);
        setProductEditor((current) => current?.id === latest.id ? { ...current, latestVersion: latest.edit_version, conflictRefreshed: true, images: [...latest.images] } : current);
        await refreshCatalog();
      } catch (error) { setActionError(error); }
    } else if (categoryEditor?.id) {
      try {
        const latest = (await getAdminCategories()).find((category) => category.id === categoryEditor.id);
        if (latest) setCategoryEditor((current) => current?.id === latest.id ? { ...current, latestVersion: latest.edit_version, conflictRefreshed: true } : current);
        await refreshCatalog();
      } catch (error) { setActionError(error); }
    }
  }

  function submitProduct(event: React.FormEvent) {
    event.preventDefault();
    if (!productEditor || (productEditor.conflict && !productEditor.conflictRefreshed)) return;
    saveProduct.mutate();
  }

  function submitCategory(event: React.FormEvent) {
    event.preventDefault();
    if (!categoryEditor || (categoryEditor.conflict && !categoryEditor.conflictRefreshed)) return;
    saveCategory.mutate();
  }

  const productConflict = getAdminApiErrorCode(saveProduct.error) === "ENTITY_CONFLICT";
  const categoryConflict = getAdminApiErrorCode(saveCategory.error) === "ENTITY_CONFLICT";

  return <AdminPageFrame route={route}>
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <AdminPanel title={t("admin.catalog.categories")}>
        <div className="flex flex-wrap gap-2">
          <button className={primaryButtonClass} onClick={() => { setCategoryEditor(blankCategoryEditor()); setActionError(null); }} type="button">{t("admin.catalog.add_category")}</button>
        </div>
        {categories.isPending ? <div className="mt-4"><AdminLoadingState /></div> : categories.isError ? <div className="mt-4"><AdminErrorState onRetry={() => void categories.refetch()} /></div> : categories.data?.length ? <ul className="mt-4 space-y-2">
          {categories.data.map((category) => <li className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-white/10" key={category.id}>
            <button className="min-h-11 min-w-0 flex-1 text-left" onClick={() => setCategoryId(category.id)} type="button"><span className="block truncate font-semibold">{language === "uz" ? category.name_uz : category.name_ru}</span><span className="text-xs text-slate-500">{category.products_count} · v{category.edit_version}</span></button>
            <button aria-label={t("admin.catalog.edit_category", { name: language === "uz" ? category.name_uz : category.name_ru })} className={buttonClass} onClick={() => editCategory(category)} type="button">{t("admin.catalog.edit")}</button>
          </li>)}
        </ul> : <div className="mt-4"><AdminEmptyState /></div>}
      </AdminPanel>

      <AdminPanel title={t("admin.catalog.products")}>
        <div className="flex min-w-0 flex-wrap items-end gap-3">
          <AdminField className="min-w-[12rem] flex-1" label={t("admin.catalog.category")}>
            {(className) => <select className={className} onChange={(event) => setCategoryId(event.target.value ? Number(event.target.value) : null)} value={categoryId ?? ""}>
              {categories.data?.map((category) => <option key={category.id} value={category.id}>{language === "uz" ? category.name_uz : category.name_ru}</option>)}
            </select>}
          </AdminField>
          <button className={primaryButtonClass} disabled={categoryId === null} onClick={() => { setProductEditor(blankProductEditor(categoryId)); setActionError(null); setPhoto(null); }} type="button">{t("admin.catalog.add_product")}</button>
        </div>
        {products.isPending ? <div className="mt-4"><AdminLoadingState /></div> : products.isError ? <div className="mt-4"><AdminErrorState onRetry={() => void products.refetch()} /></div> : products.data?.items.length ? <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 dark:border-white/10">
          <table className="w-full min-w-[34rem] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-white/5"><tr><th className="p-3">{t("admin.catalog.name_uz")}</th><th className="p-3">{t("admin.catalog.sku")}</th><th className="p-3">{t("admin.catalog.stock")}</th><th className="p-3">{t("admin.catalog.price")}</th><th className="p-3">{t("admin.catalog.edit")}</th></tr></thead>
            <tbody>{products.data.items.map((product) => <tr className="border-t border-slate-100 dark:border-white/10" key={product.id}><td className="max-w-48 truncate p-3 font-medium">{language === "uz" ? product.name_uz : product.name_ru}</td><td className="p-3">{product.sku}</td><td className="p-3">{product.stock_qty} {t(`product.unit.${product.unit}` as "product.unit.dona" | "product.unit.quti" | "product.unit.paket" | "product.unit.komplekt")}</td><td className="p-3">{formatAdminAmount(product.price)}</td><td className="p-3"><button aria-label={t("admin.catalog.edit_product", { name: language === "uz" ? product.name_uz : product.name_ru })} className={buttonClass} onClick={() => editProduct(product)} type="button">{t("admin.catalog.edit")}</button></td></tr>)}</tbody>
          </table>
        </div> : <div className="mt-4"><AdminEmptyState /></div>}
      </AdminPanel>
    </div>

    {categoryEditor && <CategoryForm
      categories={categories.data ?? []}
      editor={categoryEditor}
      conflict={categoryConflict}
      pending={saveCategory.isPending}
      error={actionError ?? saveCategory.error}
      photo={categoryPhoto}
      onClose={() => { setCategoryEditor(null); setCategoryPhoto(null); setActionError(null); saveCategory.reset(); }}
      onDraft={(draft) => setCategoryEditor((current) => current ? { ...current, draft } : current)}
      onPhoto={setCategoryPhoto}
      onRefresh={refreshConflictRecord}
      onSubmit={submitCategory}
      onUpload={() => uploadCategoryPhoto.mutate()}
      onRemovePhoto={() => removeCategoryPhoto.mutate()}
      uploading={uploadCategoryPhoto.isPending || removeCategoryPhoto.isPending}
      notice={notice}
    />}
    {productEditor && <ProductForm
      categories={categories.data ?? []}
      editor={productEditor}
      conflict={productConflict}
      pending={saveProduct.isPending}
      error={actionError ?? saveProduct.error ?? uploadProductPhoto.error ?? updateImage.error ?? removeImage.error}
      photo={photo}
      onClose={() => { setProductEditor(null); setPhoto(null); setActionError(null); saveProduct.reset(); }}
      onDraft={(draft) => setProductEditor((current) => current ? { ...current, draft } : current)}
      onPhoto={setPhoto}
      onRefresh={refreshConflictRecord}
      onSubmit={submitProduct}
      onUpload={() => uploadProductPhoto.mutate()}
      onSetImage={(imageId, isMain, sortOrder) => updateImage.mutate({ imageId, isMain, sortOrder })}
      onDeleteImage={(imageId) => removeImage.mutate(imageId)}
      uploading={uploadProductPhoto.isPending || updateImage.isPending || removeImage.isPending}
    />}
  </AdminPageFrame>;
}

function ProductForm({
  categories, editor, conflict, pending, error, photo, onClose, onDraft, onPhoto, onRefresh, onSubmit,
  onUpload, onSetImage, onDeleteImage, uploading,
}: {
  categories: AdminCategory[]; editor: ProductEditor; conflict: boolean; pending: boolean; error: unknown;
  photo: File | null; onClose: () => void; onDraft: (draft: ProductDraft) => void; onPhoto: (file: File | null) => void;
  onRefresh: () => void; onSubmit: (event: React.FormEvent) => void; onUpload: () => void;
  onSetImage: (imageId: number, main: boolean, order: number) => void; onDeleteImage: (imageId: number) => void; uploading: boolean;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const set = <K extends keyof ProductDraft>(key: K, value: ProductDraft[K]) => onDraft({ ...editor.draft, [key]: value });
  return <div className="fixed inset-0 z-40 overflow-y-auto bg-slate-950/50 p-3 sm:p-6" role="presentation">
    <section aria-labelledby="product-form-title" aria-modal="true" className="mx-auto my-2 max-w-4xl rounded-2xl bg-white p-4 shadow-2xl dark:bg-slate-950 sm:my-8 sm:p-6" role="dialog">
      <div className="flex flex-wrap items-start justify-between gap-3"><h2 className="text-xl font-semibold" id="product-form-title">{editor.id ? t("admin.catalog.edit_product", { name: language === "uz" ? editor.draft.name_uz : editor.draft.name_ru }) : t("admin.catalog.add_product")}</h2><button className={buttonClass} onClick={onClose} type="button">{t("common.cancel")}</button></div>
      <form className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
        <AdminField label={t("admin.catalog.name_uz")}>{(className) => <input className={className} maxLength={255} onChange={(event) => set("name_uz", event.target.value)} required value={editor.draft.name_uz} />}</AdminField>
        <AdminField label={t("admin.catalog.name_ru")}>{(className) => <input className={className} maxLength={255} onChange={(event) => set("name_ru", event.target.value)} required value={editor.draft.name_ru} />}</AdminField>
        <AdminField label={t("admin.catalog.description_uz")}>{(className) => <textarea className={`${className} min-h-24`} onChange={(event) => set("description_uz", event.target.value)} value={editor.draft.description_uz} />}</AdminField>
        <AdminField label={t("admin.catalog.description_ru")}>{(className) => <textarea className={`${className} min-h-24`} onChange={(event) => set("description_ru", event.target.value)} value={editor.draft.description_ru} />}</AdminField>
        <AdminField label={t("admin.catalog.sku")}>{(className) => <input className={className} maxLength={64} onChange={(event) => set("sku", event.target.value)} required value={editor.draft.sku} />}</AdminField>
        <AdminField label={t("admin.catalog.barcode")}>{(className) => <input className={className} maxLength={64} onChange={(event) => set("barcode", event.target.value)} value={editor.draft.barcode} />}</AdminField>
        <AdminField label={t("admin.catalog.category")}>{(className) => <select className={className} onChange={(event) => set("category_id", event.target.value)} required value={editor.draft.category_id}>{categories.map((category) => <option key={category.id} value={category.id}>{category.name_uz}</option>)}</select>}</AdminField>
        <AdminField label={t("admin.catalog.price")}>{(className) => <input className={className} min="0.01" onChange={(event) => set("price", event.target.value)} required step="0.01" type="number" value={editor.draft.price} />}</AdminField>
        <AdminField label={t("admin.catalog.old_price")}>{(className) => <input className={className} min="0.01" onChange={(event) => set("old_price", event.target.value)} step="0.01" type="number" value={editor.draft.old_price} />}</AdminField>
        <AdminField label={t("admin.catalog.stock")}>{(className) => <input className={className} min="0" onChange={(event) => set("stock_qty", event.target.value)} required step="1" type="number" value={editor.draft.stock_qty} />}</AdminField>
        <AdminField label={t("admin.catalog.unit")}>{(className) => <select className={className} onChange={(event) => set("unit", event.target.value as ProductDraft["unit"])} value={editor.draft.unit}>{unitOptions.map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select>}</AdminField>
        <AdminField label={t("admin.catalog.min_order_qty")}>{(className) => <input className={className} min="1" onChange={(event) => set("min_order_qty", event.target.value)} required step="1" type="number" value={editor.draft.min_order_qty} />}</AdminField>
        <AdminField label={t("admin.catalog.sort_order")}>{(className) => <input className={className} onChange={(event) => set("sort_order", event.target.value)} step="1" type="number" value={editor.draft.sort_order} />}</AdminField>
        <AdminField className="sm:col-span-2" label={t("admin.catalog.lot_url")}>{(className) => <input className={className} onChange={(event) => set("lot_url", event.target.value)} pattern="https://.+" type="url" value={editor.draft.lot_url} />}</AdminField>
        <label className="flex min-h-11 items-center gap-3 text-sm font-medium"><input checked={editor.draft.is_active} onChange={(event) => set("is_active", event.target.checked)} type="checkbox" />{t("admin.catalog.active")}</label>
        <label className="flex min-h-11 items-center gap-3 text-sm font-medium"><input checked={editor.draft.is_featured} onChange={(event) => set("is_featured", event.target.checked)} type="checkbox" />{t("admin.catalog.featured")}</label>
        <div className="sm:col-span-2">
          {conflict && <ConflictRefresh conflictRefreshed={editor.conflictRefreshed} onRefresh={onRefresh} />}
          {error != null && <AdminActionError code={getAdminApiErrorCode(error)} />}
          <div className="mt-3 flex flex-wrap gap-2"><button className={primaryButtonClass} disabled={pending || (conflict && !editor.conflictRefreshed)} type="submit">{pending ? t("admin.common.loading") : t("admin.catalog.save_product")}</button></div>
        </div>
      </form>

      {editor.id !== null && <section className="mt-6 border-t border-slate-200 pt-4 dark:border-white/10">
        <h3 className="font-semibold">{t("admin.catalog.product_photo")}</h3>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <AdminField label={t("admin.catalog.product_photo")}>{(className) => <input accept="image/jpeg,image/png,image/webp" className={className} onChange={(event) => onPhoto(event.target.files?.[0] ?? null)} type="file" />}</AdminField>
          <button className={buttonClass} disabled={!photo || uploading} onClick={onUpload} type="button">{t("admin.catalog.upload_photo")}</button>
        </div>
        <ul className="mt-3 space-y-2">{editor.images.map((image, index) => <li className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-white/10" key={image.id}>
          <span className="min-w-0 truncate text-sm">{image.url ?? image.telegram_file_id ?? `#${image.id}`} {image.is_main && <strong>· {t("admin.catalog.set_primary")}</strong>}</span>
          <div className="flex flex-wrap gap-2">
            <button className={buttonClass} disabled={uploading || image.is_main} onClick={() => onSetImage(image.id, true, image.sort_order)} type="button">{t("admin.catalog.set_primary")}</button>
            <button className={buttonClass} disabled={uploading || index === 0} onClick={() => onSetImage(image.id, image.is_main, Math.max(0, image.sort_order - 1))} type="button">{t("admin.catalog.move_up")}</button>
            <button className={buttonClass} disabled={uploading || index === editor.images.length - 1} onClick={() => onSetImage(image.id, image.is_main, image.sort_order + 1)} type="button">{t("admin.catalog.move_down")}</button>
            <button className={buttonClass} disabled={uploading} onClick={() => onDeleteImage(image.id)} type="button">{t("admin.catalog.delete_photo")}</button>
          </div>
        </li>)}</ul>
      </section>}
    </section>
  </div>;
}

function CategoryForm({
  categories, editor, conflict, pending, error, photo, onClose, onDraft, onPhoto, onRefresh,
  onSubmit, onUpload, onRemovePhoto, uploading, notice,
}: {
  categories: AdminCategory[]; editor: CategoryEditor; conflict: boolean; pending: boolean; error: unknown;
  photo: File | null; onClose: () => void; onDraft: (draft: CategoryDraft) => void;
  onPhoto: (file: File | null) => void; onRefresh: () => void; onSubmit: (event: React.FormEvent) => void;
  onUpload: () => void; onRemovePhoto: () => void; uploading: boolean; notice: string;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const set = <K extends keyof CategoryDraft>(key: K, value: CategoryDraft[K]) => onDraft({ ...editor.draft, [key]: value });
  const current = categories.find((item) => item.id === editor.id);
  return <div className="fixed inset-0 z-40 overflow-y-auto bg-slate-950/50 p-3 sm:p-6" role="presentation">
    <section aria-labelledby="category-form-title" aria-modal="true" className="mx-auto my-2 max-w-2xl rounded-2xl bg-white p-4 shadow-2xl dark:bg-slate-950 sm:my-8 sm:p-6" role="dialog">
      <div className="flex flex-wrap items-start justify-between gap-3"><h2 className="text-xl font-semibold" id="category-form-title">{editor.id ? t("admin.catalog.edit_category", { name: language === "uz" ? editor.draft.name_uz : editor.draft.name_ru }) : t("admin.catalog.add_category")}</h2><button className={buttonClass} onClick={onClose} type="button">{t("common.cancel")}</button></div>
      <form className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
        <AdminField label={t("admin.catalog.name_uz")}>{(className) => <input className={className} maxLength={128} onChange={(event) => set("name_uz", event.target.value)} required value={editor.draft.name_uz} />}</AdminField>
        <AdminField label={t("admin.catalog.name_ru")}>{(className) => <input className={className} maxLength={128} onChange={(event) => set("name_ru", event.target.value)} required value={editor.draft.name_ru} />}</AdminField>
        <AdminField label={t("admin.catalog.description_uz")}>{(className) => <textarea className={`${className} min-h-24`} onChange={(event) => set("description_uz", event.target.value)} value={editor.draft.description_uz} />}</AdminField>
        <AdminField label={t("admin.catalog.description_ru")}>{(className) => <textarea className={`${className} min-h-24`} onChange={(event) => set("description_ru", event.target.value)} value={editor.draft.description_ru} />}</AdminField>
        <AdminField label={t("admin.catalog.category")}>{(className) => <select className={className} onChange={(event) => set("parent_id", event.target.value)} value={editor.draft.parent_id}><option value="">—</option>{categories.filter((category) => category.id !== editor.id).map((category) => <option key={category.id} value={category.id}>{language === "uz" ? category.name_uz : category.name_ru}</option>)}</select>}</AdminField>
        <AdminField label={t("admin.catalog.sort_order")}>{(className) => <input className={className} onChange={(event) => set("sort_order", event.target.value)} step="1" type="number" value={editor.draft.sort_order} />}</AdminField>
        {editor.id !== null && <label className="flex min-h-11 items-center gap-3 text-sm font-medium"><input checked={editor.draft.is_active} onChange={(event) => set("is_active", event.target.checked)} type="checkbox" />{t("admin.catalog.active")}</label>}
        <div className="sm:col-span-2">{conflict && <ConflictRefresh conflictRefreshed={editor.conflictRefreshed} onRefresh={onRefresh} />}{error != null && <AdminActionError code={getAdminApiErrorCode(error)} />}<div className="mt-3 flex gap-2"><button className={primaryButtonClass} disabled={pending || (conflict && !editor.conflictRefreshed)} type="submit">{t("admin.catalog.save_category")}</button></div></div>
      </form>
      {editor.id !== null && <section className="mt-5 border-t border-slate-200 pt-4 dark:border-white/10"><h3 className="font-semibold">{t("admin.catalog.category_photo")}</h3>
        {current?.image_url && <button className={`${buttonClass} mt-2`} disabled={uploading} onClick={onRemovePhoto} type="button">{t("admin.catalog.delete_photo")}</button>}
        <div className="mt-3 flex flex-wrap items-end gap-3"><AdminField label={t("admin.catalog.category_photo")}>{(className) => <input accept="image/jpeg,image/png,image/webp" className={className} onChange={(event) => onPhoto(event.target.files?.[0] ?? null)} type="file" />}</AdminField><button className={buttonClass} disabled={!photo || uploading} onClick={onUpload} type="button">{t("admin.catalog.upload_photo")}</button></div>
      </section>}
      {notice && <p className="mt-3 text-sm text-emerald-700" role="status">{notice}</p>}
    </section>
  </div>;
}

function ConflictRefresh({ conflictRefreshed, onRefresh }: { conflictRefreshed: boolean; onRefresh: () => void }) {
  const t = useTranslate();
  return <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-300/30 dark:bg-amber-300/10">
    <p className="text-sm text-amber-900 dark:text-amber-100">{conflictRefreshed ? t("admin.common.conflict_refreshed") : t("admin.common.conflict")}</p>
    {!conflictRefreshed && <button className={`${buttonClass} mt-2`} onClick={onRefresh} type="button">{t("admin.common.refresh_latest")}</button>}
  </div>;
}

function blankProductEditor(categoryId: number | null): ProductEditor {
  return { id: null, version: 0, latestVersion: null, conflict: false, conflictRefreshed: false, images: [], draft: {
    category_id: categoryId === null ? "" : String(categoryId), name_uz: "", name_ru: "", description_uz: "", description_ru: "", sku: "", barcode: "", price: "", old_price: "", stock_qty: "0", unit: "dona", min_order_qty: "1", is_active: true, is_featured: false, sort_order: "0", lot_url: "",
  } };
}

function productDraft(product: AdminProduct): ProductDraft {
  return {
    category_id: String(product.category_id), name_uz: product.name_uz, name_ru: product.name_ru,
    description_uz: product.description_uz ?? "", description_ru: product.description_ru ?? "",
    sku: product.sku, barcode: product.barcode ?? "", price: String(product.price), old_price: product.old_price === null ? "" : String(product.old_price),
    stock_qty: String(product.stock_qty), unit: product.unit, min_order_qty: String(product.min_order_qty), is_active: product.is_active,
    is_featured: product.is_featured, sort_order: String(product.sort_order), lot_url: product.lot_url ?? "",
  };
}

function productBody(draft: ProductDraft, includeActive: boolean) {
  const body: Record<string, unknown> = {
    category_id: Number(draft.category_id), name_uz: draft.name_uz.trim(), name_ru: draft.name_ru.trim(),
    description_uz: nullable(draft.description_uz), description_ru: nullable(draft.description_ru),
    sku: draft.sku.trim(), barcode: nullable(draft.barcode), price: draft.price, old_price: nullable(draft.old_price),
    stock_qty: Number(draft.stock_qty), unit: draft.unit, min_order_qty: Number(draft.min_order_qty),
    is_featured: draft.is_featured, sort_order: Number(draft.sort_order), lot_url: nullable(draft.lot_url),
  };
  if (includeActive) body.is_active = draft.is_active;
  return body;
}

function blankCategoryEditor(): CategoryEditor {
  return { id: null, version: 0, latestVersion: null, conflict: false, conflictRefreshed: false, draft: { parent_id: "", name_uz: "", name_ru: "", description_uz: "", description_ru: "", sort_order: "0", is_active: true } };
}

function categoryDraft(category: AdminCategory): CategoryDraft {
  return { parent_id: category.parent_id === null ? "" : String(category.parent_id), name_uz: category.name_uz, name_ru: category.name_ru, description_uz: category.description_uz ?? "", description_ru: category.description_ru ?? "", sort_order: String(category.sort_order), is_active: category.is_active };
}

function categoryBody(draft: CategoryDraft, includeActive: boolean) {
  return {
    parent_id: draft.parent_id === "" ? null : Number(draft.parent_id),
    name_uz: draft.name_uz.trim(),
    name_ru: draft.name_ru.trim(),
    description_uz: nullable(draft.description_uz),
    description_ru: nullable(draft.description_ru),
    sort_order: Number(draft.sort_order),
    ...(includeActive ? { is_active: draft.is_active } : {}),
  };
}

function nullable(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}
