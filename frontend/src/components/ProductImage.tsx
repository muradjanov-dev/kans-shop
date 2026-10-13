import { useState } from 'react';
import { StationeryArt } from '@/components/StationeryArt';
import { useLanguageStore } from '@/store/language';
import { localizedField } from '@/lib/format';
import type { Product } from '@/types/api';

export function ProductImage({ product, className = '' }: { product: Product; className?: string }) {
  const language = useLanguageStore(state => state.language);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const image = product.images.find(image => image.is_main && image.url) ?? product.images.find(image => image.url);
  const name = localizedField(language, product, 'name');
  if (image?.url && image.url !== failedUrl) {
    return <img src={image.url} alt={name} loading="lazy" decoding="async" onError={() => setFailedUrl(image.url)} className={`size-full object-contain ${className}`} />;
  }
  return <div className={`flex size-full items-center justify-center bg-[#EDF1E7] ${className}`} role="img" aria-label={`${name} — ${language === 'ru' ? 'иллюстрация, фото пока нет' : 'illyustratsiya, surat hali yo‘q'}`}><StationeryArt variant={`${product.sku} ${product.name_uz}`} className="h-full w-full max-w-72" /></div>;
}
