# Kans Shop vitrinasi va mijoz kabineti dizayni

**Holat:** Owner Phase 3 yozma dizaynini 2026-10-09 kuni tasdiqladi va rejalarni yozib, darhol avtonom implementatsiyaga o‘tishni so‘radi.

Kans Shop bitta do‘kon bo‘lib qoladi. Bu bosqich Telegram Mini App va oddiy brauzerda katalogni topish, mahsulotni tushunish va buyurtma holatini kuzatishni yaxshilaydi. Safran va Tezqurbot vizual va navigatsiya namunalari; ularning biznes modeli yoki to‘ldirilgan ma’lumotlari ko‘chirilmaydi.

## Tasdiqlangan yo‘nalish

Phase 1 mijozni Telegram hisobiga bog‘laydi: Mini App `initData` bilan, brauzer esa botdan olingan bir martalik kod bilan kiradi. Mehmon katalogni ko‘radi, lekin server savatiga qo‘shishdan oldin kiradi. Brauzer va Mini App bitta server savati hamda buyurtmalar tarixidan foydalanadi.

Phase 2 haqiqiy katalog, mahsulot rasmlari, kategoriyalar va do‘kon sozlamalarini web admin orqali boshqarishni beradi. Phase 3 support, ish vaqti, welcome matni, mavjud narx sozlamalari yoki mahsulot holati uchun taxminiy qiymat kiritmaydi.

Phase 3 doirasi:

- Bitta do‘kon uchun mobil va desktop vitrina.
- Kategoriya daraxti, qidiruv, server pagination, filtrlar va saralash.
- Mahsulot rasmlar galereyasi va mavjud mahsulot ma’lumotlari.
- Kirgan mijoz uchun profil, sevimlilar va saqlangan manzillar.
- Buyurtma tarixi, xavfsiz status timeline va sozlangan support aloqa yo‘li.
- O‘zbek va rus tillari, qulay klaviatura va touch navigatsiya.

Bu bosqichda sotuvchilar katalogi, mehmon savati, xaritasiz tasdiqlanmagan delivery va’dasi, geocoding, yangi to‘lov provayderi, review/reyting, soxta chegirma yoki mavjud bo‘lmagan “bestseller” belgisi yaratilmaydi.

## Vizual yo‘nalish

Kans Shop’ning hozirgi binafsha rang aksenti qoladi. Oqartirilgan yoki to‘q neytral sathlar, aniq matn kontrasti, yengil kartalar, bo‘sh joy va real mahsulot suratlari asosiy ko‘rinishni beradi. Yaltiroq effektlar matn va narxni bosib ketmaydi.

Safran’dagi ko‘rinadigan til tanlash, aniq navigatsiya va Telegram orqaga qaytish xatti-harakati; Tezqurbot’dagi desktop/mobile ustunlar va kategoriya suratlari moslashtiriladi. Kans o‘zining markasi, ranglari va real kontentidan foydalanadi.

Featured bo‘lim faqat admin belgilagan `is_featured` mahsulotlar bor bo‘lsa ko‘rinadi. Welcome matni Phase 2’da tasdiqlanib sozlanadi. Hech bir mahsulot yo‘q bo‘lsa promo banner yoki demo mahsulot bilan joy to‘ldirilmaydi.

Mobil ko‘rinishda ikki ustunli katalog, barmoq bilan bosishga qulay tugmalar va asosiy qisqa navigatsiya saqlanadi. Keng ekranda mazmun markazda cheklanadi, katalog odatda to‘rt ustunga kengayadi, mahsulot sahifasi rasm va tafsilotni yonma-yon ko‘rsatadi. Oraliq kengliklarda ustunlar ekranga moslashadi.

Har bir amalda ko‘rinadigan fokus, matnli accessible label, kamida 44px bosish maydoni va qisqartirilgan animatsiya (`prefers-reduced-motion`) qo‘llanadi. Icon yoki rang yolg‘iz o‘zi amaliy holatni bildirmaydi. Mobil va desktop’da light/dark mavzular katalog, savat, checkout, kabinet va dialoglarda izchil qo‘llanadi; matnning o‘qilishi va tugma kontrasti tekshiriladi.

## Sahifalar va navigatsiya

Mavjud `/`, `/product/:id`, `/cart`, `/checkout`, `/orders` va `/orders/:id` URL’lari saqlanadi. `/` do‘konning katalogga yo‘naltiruvchi bosh sahifasi bo‘ladi; qidiruv, kategoriya va filtrlar URL query parametrlarida ifodalanadi. Mahsulotdan orqaga qaytganda oldingi qidiruv, filter va scroll holati saqlanadi.

Yangi mijoz yo‘llari `/profile`, `/favorites` va `/profile/addresses` bo‘ladi. Mobil navigatsiya katalog, savat, buyurtmalar va profilni beradi; sevimlilar profildan ochiladi. Desktop header brend, qidiruv, katalog, buyurtmalar, savat, profil va til almashtirishni ko‘rsatadi. Support havolasi faqat sozlangan bo‘lsa chiqadi.

## Bosh sahifa va katalog

Public katalog mavjud FastAPI ma’lumotlaridan yig‘iladi. Bosh sahifa `welcome_text_uz`/`welcome_text_ru` sozlamasi bor bo‘lsa ko‘rsatadi, root kategoriyalarni surat va nom bilan chiqaradi, keyin haqiqiy featured mahsulotlarni ko‘rsatadi. Pastdagi barcha faol mahsulotlar grid’i featured flag yoki kategoriya tanlashga bog‘liq bo‘lmaydi. Matn yoki surat yo‘q bo‘lsa uydirma biznes da’vosi yaratilmaydi.

Kategoriya daraxti mavjud `parent_id` ierarxiyasini qo‘llaydi: root’dan keyingi child’lar va breadcrumb orqali navigatsiya qilinadi; UI ikki daraja bilan sun’iy cheklanmaydi. Mijoz barcha root kategoriyalarni ko‘ra oladi va kerak bo‘lsa “barcha kategoriyalar”ga qaytadi. Kategoriya `image_url` bo‘lsa surat ishlatiladi; yo‘q bo‘lsa oddiy neytral fallback beriladi. Faqat faol mahsulot va barcha faol category ancestor’lari bo‘lgan mahsulot ko‘rinadi. Faolsiz parent yoki buzilgan/cyclic ierarxiya ostidagi mahsulot public katalogdan chiqarilmaydi; admin uchun tuzatish holati ko‘rsatiladi.

Qidiruv o‘zbek va ruscha mahsulot nomlarida server orqali ishlaydi. Inputdan keyin 300ms tinchlik bo‘lmaguncha request yuborilmaydi. Qidiruv matni, kategoriya, filtr, saralash va sahifa URL’da saqlanadi; input o‘zgarsa sahifa 1 ga qaytadi.

Kategoriyadagi mahsulotlar va qidiruv natijalari 24 tadan olinadi. “Yana ko‘rsatish” keyingi sahifani qo‘shadi; mavjud mahsulotlar ekrandan yo‘qolmaydi. Sahifa tugashi, natija yo‘qligi, yuklanish, tarmoq xatosi va rate limit holatlari alohida ko‘rinadi. Qayta urinish filter/query qiymatlarini saqlaydi.

Filtrlar:

- Eng kam va eng yuqori narx. Qiymatlar serverga decimal matn sifatida yuboriladi; manfiy qiymat va minimum maksimumdan katta bo‘lishi validatsiya xatosi bo‘ladi.
- Faqat sotib olishga yetarli miqdori mavjud mahsulotlar (`in_stock`): `stock_qty >= min_order_qty` va `stock_qty > 0`.
- Saralash: standart tartib, narx o‘sish, narx kamayish va yangilik.

Standart saralash kategoriyada joriy `sort_order, id`, qidiruvda server relevanti saqlaydi. Narx saralashda teng qiymatlar `id` bilan barqarorlashtiriladi; yangilik `created_at DESC, id DESC` bo‘yicha ishlaydi. Filtrlar React’da yuklangan 24 mahsulotga qo‘llanmaydi. Natija nol bo‘lsa aniq empty state va filterlarni tozalash yo‘li ko‘rsatiladi; mavjud bo‘lmagan mahsulot yoki natija soni bilan sahifa to‘ldirilmaydi.

## Mahsulot sahifasi

Mahsulot nomi va tavsifi tanlangan `uz` yoki `ru` maydonidan olinadi. `Product.images` gallery bo‘ladi: asosiy rasm birinchi ochiladi, thumbnail yoki swipe boshqa mavjud suratlarni ko‘rsatadi. Bo‘sh yoki yuklanmagan rasmda broken-image icon o‘rniga neytral placeholder ishlatiladi; katalog image xatosini boshqa mahsulot surati bilan almashtirmaydi.

Mahsulot kartasi va detail quyidagilarni ko‘rsatadi: joriy narx, units (`dona`, `quti`, `paket`, `komplekt`), SKU, stock, minimal miqdor va bor bo‘lsa eski narx. Eski narx faqat joriy narxdan yuqori bo‘lsa solishtirish uchun ko‘rsatiladi. Featured belgisi faqat serverdagi `is_featured=true` qiymatiga tayangan holda chiqadi.

Tanlangan miqdor `min_order_qty`dan boshlanadi va `stock_qty`dan oshmaydi. Stock minimumdan kam bo‘lsa sotib olish boshqaruvi o‘chiriladi va sababi yoziladi. Server stock va narxning yakuniy manbai bo‘lib qoladi.

## Mijoz profili va sevimlilar

`GET/PATCH /api/v1/profile` faqat kirgan mijozga tegishli profilni qaytaradi yoki yangilaydi. Javob faqat `display_name`, `phone` va `language` maydonlarini o‘z ichiga oladi. `display_name` users jadvalida alohida saqlanadi; eski foydalanuvchilar uchun Telegram ism-familiyasidan boshlang‘ich qiymat olinadi. Ism trim qilingandan keyin 1–128 belgili bo‘ladi. `phone` mavjud `users.phone` ustunida saqlanadi va server O‘zbekiston telefon raqamini validatsiya qiladi; bo‘sh profil telefoni `null` bo‘lishi mumkin, checkout telefonini esa baribir talab qiladi. `language` faqat `uz` yoki `ru` bo‘ladi va bot bilan umumiy `users.language` qiymatini yangilaydi. Keyingi bot/web checkout formasi shu display name/phone’dan boshlanadi, mijoz esa buyurtma uchun boshqa qiymat kiritishi mumkin; formani yuborish profilni yashirincha o‘zgartirmaydi.

Telegram ID, username, admin flag va rol tahrirlanmaydi hamda mijoz profil API’si bu qiymatlarni qabul qilmaydi. Profile form telefon, ism yoki tilni yangilashni alohida xabar qiladi. Profile va shaxsiy ma’lumotlar 401/403 yoki tarmoq xatosida tozalanib ketmaydi.

Sevimlilar mavjud `favorites` jadvali va repository’idan foydalanadi; brauzerda alohida local favorites nusxasi bo‘lmaydi. `GET /api/v1/favorites?page&limit` faol mahsulotlar bilan sahifalangan ro‘yxat beradi. `PUT /api/v1/favorites/{product_id}` qo‘shishni, `DELETE` olib tashlashni idempotent bajaradi. Mahsulot detail’dagi yurak va sevimlilar sahifasi shu server holatini ishlatadi.

Sevimlilar mehmon uchun yozilmaydi. Mehmon yurakni bossa Phase 1’dagi mijoz login oynasi chiqadi va bitta pending `favorite_add` amali login tugaguncha saqlanadi; login’dan keyin bir marta bajariladi. Shu mexanizm savat qo‘shish intent’ini bekor qilmaydi, intent turi aniq ajratiladi. Ikkinchi amal login oynasida birinchisini yashirincha almashtirmaydi.

## Saqlangan manzillar

`GET/POST /api/v1/addresses`, `PATCH/DELETE /api/v1/addresses/{address_id}` va `PUT /api/v1/addresses/{address_id}/default` manzil kitobini boshqaradi. Har amal `get_current_user`dan aniqlangan owner’ni ishlatadi; URL’dagi id boshqa mijozga tegishli bo‘lsa API mavjudligini oshkor qilmasdan not-found javob beradi.

Manzil maydonlari `label` (1–60 belgi), `address_text` (1–1000), ixtiyoriy `address_comment` (ko‘pi bilan 500) va `is_default`; matnlar trim qilinadi. Bir mijoz ko‘pi bilan 20 manzil saqlaydi. Manzil faqat matn va mijoz kiritgan izohdan iborat; koordinata, xarita, geocoding yoki avtomatik manzil aniqlash yo‘q. Ko‘pi bilan bitta manzil default bo‘ladi; create/default/delete user row lock ostida bajariladi va `(user_id)` uchun default=true partial unique index shu invariantni ham tekshiradi. Birinchi manzil default bo‘ladi; default o‘chirilgach qolganlari avtomatik tanlanmaydi va mijoz keyingi checkout’da bittasini tanlaydi.

Profil manzilni qo‘shish, tahrirlash, default qilish va o‘chirish imkonini beradi. Delivery checkout saqlangan manzildan foydalanishi yoki yangi, hozirgi buyurtmaga tegishli matn kiritishi mumkin. “Keyingi safar saqlash” tanlansa manzil API orqali alohida saqlanadi. Pickup va preorder manzil so‘ramaydi.

Manzil tanlanganda server qaytargan `address_text` va `address_comment` checkout formasiga ko‘chiriladi va mijoz tasdiqlagan shu matn yangi order snapshot’iga yoziladi. Manzil kitobi boshqa tabda o‘zgarsa forma yashirincha almashtirilmaydi; qayta tanlash yangi qiymatlarni yuklaydi. Idempotency payload fingerprint’i tasdiqlangan matn va comment’ni o‘z ichiga oladi; saved address ID order contract’iga qo‘shilmaydi. Phase 1 quote fingerprint’i order type va narxga ta’sir qiluvchi qiymatlarni tekshiradi; manzil kitobi delivery haqi yoki hududini frontendda hisoblamaydi. Keyin manzil o‘zgartirilsa yoki o‘chirilsa eski buyurtma snapshot’i o‘zgarmaydi.

## Buyurtmalar, timeline va support

Mavjud `GET /orders` va `GET /orders/{id}` kontraktlari saqlanadi. Yangi `GET /api/v1/orders/history?page&limit` customer uchun sahifalangan buyurtmalar beradi. Ro‘yxatda order number, sana, status, payment status, order type va server total ko‘rinadi. Detail snapshot itemlar, address, payment method/status, upload qilingan chek holati va Phase 1 private receipt/payment recovery yo‘lini ishlatadi.

`GET /api/v1/orders/{order_id}/timeline` faqat order egasiga ruxsat beradi. U `order_status_history`dan mijozga ko‘rinadigan `status` va `occurred_at`ni qaytaradi; admin ID, admin nomi va history `comment` yuborilmaydi. Statuslar mavjud lifecycle’ga mos tarjima qilinadi. Haqiqiy o‘tgan event’lar bajarilgan, joriy status faol, kelajakdagi bosqichlar kutilayotgan ko‘rinadi; `cancelled` alohida terminal branch bo‘ladi va buyurtmani `completed` ko‘rsatmaydi. Timeline bo‘sh yoki buzilgan bo‘lsa faqat mavjud current status ko‘rsatiladi, timestamp taxmin qilinmaydi. Live courier joylashuvi, yetib borish vaqti yoki kuzatilmaydigan bosqichlar ixtiro qilinmaydi.

Public support faqat Phase 2’da haqiqiy `support_username`, `shop_phone` yoki `work_hours` sozlanganda ko‘rinadi. Telegram havolasi va `tel:` link faqat yaroqli qiymatdan tuziladi. Qiymat bo‘sh bo‘lsa o‘lik tugma yoki “admin bilan bog‘laning” uydirmasi chiqmaydi. Support havolasi barcha sahifalardan topilishi mumkin, lekin checkoutni yopmaydi.

Do‘kon ochiq emas, kerakli fee/minimum qiymati yo‘q yoki to‘lov rekviziti sozlanmagan bo‘lsa Phase 1’dagi checkout-unavailable holati aniq ko‘rsatiladi. Catalog, profil va oldingi buyurtmalar ochiq qoladi. Narx, delivery fee, minimum, payment method readiness va total backend’dan olinadi; front-end bu moliyaviy qoidalarni takrorlamaydi.

## API va xavfsizlik

Mavjud katalog API’lari backward-compatible kengayadi:

- `GET /catalog/products` barcha faol, faol ancestor kategoriyalarga tegishli mahsulotlarning sahifalangan grid’ini beradi; optional `category_id`, narx/stock/sort filterlari shu umumiy catalog service’dan o‘tadi.
- `GET /catalog/categories?parent_id=...` root va child kategoriyalarni beradi; inactive parent ostidagi kategoriya qaytarilmaydi.
- `GET /catalog/categories/{id}/products` va `GET /catalog/search` `page`, `limit=24`, `min_price`, `max_price`, `in_stock`, `sort` parametrlarini qabul qiladi.
- `GET /catalog/featured?limit=...` faqat faol, admin featured qilgan mahsulotlarni qaytaradi; bo‘sh ro‘yxat normal natija.
- `GET /catalog/products/{id}` mavjud `ProductOut.images` va mahsulot maydonlarini saqlaydi. Kategoriya, search, featured va detail javoblarining barchasi mahsulotni uning barcha ancestor kategoriyalari faol bo‘lsagina chiqaradi.
- `GET /settings/public` Phase 2’dagi public allowlist bilan support, hours va welcome matnini beradi; payment secret va admin ma’lumoti hech qachon public bo‘lmaydi.

Yangi profile, favorites, addresses, order history va timeline API’lari bearer-auth talab qiladi. Har repository query user ID’ni token’dan olingan `get_current_user` bilan cheklaydi. Mijoz yuborgan user ID, Telegram ID yoki rolga ishonilmaydi. Order timeline faqat status va vaqtni oshkor qiladi. Product rasmlari public katalog media bo‘lib qoladi; receipt faqat Phase 1’dagi private authenticated API orqali ochiladi.

Query parametrlari serverda validatsiya qilinadi. Noto‘g‘ri price range 422, auth yo‘qligi 401, foreign profile/address/order 404 yoki mavjud API qoidalariga mos 403, limit buzilishi 422 qaytaradi. 429 qidiruv yoki auth chegarasini tushuntiradi; 5xx/offline holatda qidiruv, filter, manzil formasi va account state saqlanadi. API stack trace yoki secret foydalanuvchiga chiqarilmaydi.

Server modul chegaralari:

- `catalog_service` ancestor holati, stock, filtr, tartib va pagination’ni bitta joyda belgilaydi; route query qiymatlarini tekshiradi va service’ga uzatadi.
- `profile_service` faqat mijozga ko‘rinadigan profile field’larini o‘qiydi/yangilaydi; Telegram ID va rolga setter yo‘q.
- Mavjud `Favorite` model/repository asosida umumiy `favorite_service` yaratiladi; aiogram customer katalogi va web API bitta user-scoped xizmatni ishlatadi. Botdan yoki web’dan saqlangan mahsulot ikkala client’da ko‘rinadi; alohida favorites jadvali yaratilmaydi.
- `address_service` default-address yaxlitligi va owner checks’ni bajaradi; `order_service` esa order’ga faqat checkout paytidagi address snapshot’ni yozadi.
- `order_service` yoki order repository status history’ni `timeline` contract’iga tozalaydi; UI raw ORM history/comment’ni o‘qimaydi.
- React sahifalar typed TanStack Query hooks orqali API’ga chiqadi. Component’lar narx, zaxira, permission yoki order status qoidalarining manbai bo‘lmaydi.

## Frontend modullari va holat

Mavjud `App.tsx`, `Layout.tsx`, Router va TanStack Query davom etadi. Root route va mahsulot/savat/checkout/buyurtma URL’lari saqlanadi; profile/favorites/addresses uchun yangi route’lar qo‘shiladi. Desktop header/mobile navigation alohida `components/storefront/` modullarida bo‘ladi.

Katalog qidiruv/filter query holati URL va React Query key’iga bir xil normalizatsiyada kiradi. 300ms debounce’dan oldin search request yo‘q; har filter o‘zgarishi page’ni 1 ga qaytaradi. 24 ta mahsulot lazy image bilan olinadi; “yana ko‘rsatish” shu query bo‘yicha keyingi page’ni qo‘shadi. Query cache katalog, filter va page bo‘yicha ajratiladi.

Profil, sevimlilar, manzillar, buyurtmalar va timeline mijozga tegishli cache key’lardan foydalanadi. Login, logout yoki account almashtirishda shaxsiy query cache tozalanadi; Phase 1 auth epoch qoidasi eski account’ning kechikkan javobini yangi account cache’iga yozdirmaydi. Favorite/address mutation mos query’ni yangilaydi yoki invalidate qiladi; public catalogni mijozga tegishli maydonlar bilan umumiy cache’da aralashtirmaydi. Favorites eager loading mahsulot rasmlarini ham oladi: yangi sessiyada serializatsiya hidden async query bajarmaydi.

Tillar `uz` va `ru`; barcha interface xabarlari dictionary orqali keladi, mahsulot va kategoriya maydonlari server lokalizatsiyasidan foydalanadi. Kirgan mijozning tanlovi `/profile` orqali saqlanib bot bilan bir xil `users.language`ga sinxronlanadi. Mehmon browser tanlovi local preference bo‘ladi; Mini App’ning ilk tili Telegram tilidan aniqlanadi, keyingi qo‘lda tanlov avtomatik override qilinmaydi.

Yuklanish, bo‘sh ro‘yxat, filter natijasi yo‘qligi, ruxsatsiz kirish, 401 refresh, 403, 404, validation 422, conflict 409, rate limit 429, offline va server 5xx holatlari har bir sahifa uchun ko‘rsatiladi. Qayta urinish user kiritgan qiymat va URL state’ni tozalamasdan ishlaydi.

## Test va qabul mezonlari

Backend uchun existing disposable PostgreSQL/Redis test muhiti ishlatiladi. Testlar profile owner checks va field allowlist’ni, UZ phone/language validation’ni, default address uniqueness/ownership’ni, manzil snapshot’ining eski order’dan mustaqilligini, favorites idempotency’ni, filter/sort/pagination tie-break’larini hamda timeline’da admin ID/comment yo‘qligini tekshiradi.

Frontend unit/component testlari Vitest, React Testing Library va jsdom’dan foydalanadi; customer API’lari fake bo‘ladi. Playwright faqat bir necha asosiy browser journey’ni tekshiradi va `/api/v1`ni fixture bilan intercept qiladi. Test hech qachon production bot, DB, telefon yoki order’iga ulanmaydi.

Qabul shartlari:

- UZ va RU’da kategoriya, qidiruv, filtr, saralash, page va product back-navigation URL state bilan ishlaydi.
- 300ms ichida yozilgan keyingi belgi pending debounce’ni yangilaydi; boshlanib bo‘lgan eski query request’i AbortSignal bilan bekor qilinadi va uning kech javobi yangi natijani almashtirmaydi. Natijalar 24 tadan qo‘shiladi, shu query’da oldin ko‘rsatilgan mahsulotlar saqlanadi va ID bo‘yicha takrorlar chiqarilmaydi.
- Stock/minimum miqdori noto‘g‘ri mahsulotni savatga yubormaydi; narx va checkout total faqat server quote’dan keladi.
- Anonymous user katalogni ko‘radi; sevimli yoki savat action’i kerakli login dialogini ochadi va bir pending action’ni bir marta bajaradi.
- Profile’dagi name/phone/language update faqat shu Telegram user’ga yoziladi; Telegram ID va role o‘zgarmaydi.
- Manzil create/edit/delete/default boshqa foydalanuvchi manziliga ta’sir qilmaydi; parallel create/default’da ko‘pi bilan bitta default va 20 manzil limiti saqlanadi; checkout snapshot’i keyingi edit/delete’dan o‘zgarmaydi.
- Favorite state refresh, browser va Mini App orasida shu server user uchun sinxron qoladi; logout’dan keyin boshqa account cache’i ko‘rinmaydi.
- Bot customer catalog’da qo‘shilgan yoki olib tashlangan favorite web favorites ro‘yxatida, web’dan qilingan amal bot ro‘yxatida bir xil Telegram user uchun ko‘rinadi.
- Inactive root/category ancestor yoki cyclic ierarxiya ostidagi mahsulot va kategoriya public API’da ko‘rinmaydi; uch va undan ko‘p daraja navigatsiyasi, missing image fallback va 0 natija filter reset tekshiriladi. In-stock filter minimum miqdorini qoplay olmaydigan mahsulotni chiqarmaydi.
- Timeline real status/time’ni ko‘rsatadi, kelajak bosqichi bajarilgan bo‘lmaydi, cancelled terminal branch; admin nomi/comment’i yo‘q va foreign order timeline olinmaydi.
- Support link va welcome matni real sozlamadan keladi; null contact yoki fee/payment qiymati uydirma bilan to‘ldirilmaydi.
- 375px atrofidagi mobile va 1280px+ desktop, Uzbek va Russian matn uzunligi, klaviatura/fokus va 44px bosish maydoni tekshiriladi.

Playwright’dagi synthetic Telegram global API va fake HTTP javoblari haqiqiy Telegram testini almashtirmaydi. Oxirgi acceptance alohida test bot/katalog bilan Mini App’ning native Telegram WebView’ida, UZ va RU tanlangan foydalanuvchilar bilan o‘tkaziladi. Mobil/desktop va light/dark screenshot’lar visual QA uchun saqlanadi; ular funksional testlarning o‘rnini bosmaydi.

## Release’ga bog‘liqlik va owner ma’lumotlari

Phase 2 web admin profile/catalog, category image, featured flag, support, work hours, welcome text va public store setting’larni boshqarish imkonini beradi. Shu qiymatlar kiritilmaguncha Phase 3 o‘lik aloqa tugmasi yoki taxminiy marketing matni ko‘rsatmaydi. Exact delivery fee, free delivery threshold, minimum order, kartadagi rekvizit va online provider launch tanlovi owner tomonidan keyinroq belgilanadi; bu dizayn ularga qiymat to‘qimaydi.

DB schema o‘zgarishi `display_name` va addresses jadvali/migration’ni, favorites modelida yangi duplicate jadval yaratmasdan API/service qo‘shimchani talab qiladi. Migration Phase 2’ning yakuniy head’idan davom etadi; parallel Alembic head yaratilmaydi. Eski order address/comment item snapshot’lari o‘zgarmaydi. Seed yoki demo ma’lumoti production catalog, karta yoki contact setting’ini almashtirmaydi.

CI’da backend lint/typecheck/test hamda frontend `npm ci`, `npm run typecheck`, `npm run build`, Vitest va Playwright journey’lari o‘tadi. Migration eski schema nusxasida tekshiriladi. Yangi web API’lar eski katalog, cart, checkout va order URL’lariga mos additive contract saqlaydi. Release faqat testdagi, fake-account xarid bilan tekshiriladi; production’da real buyurtma yoki real to‘lov acceptance testi bo‘lmaydi.

Vitrina uchun production visual review UZ/RU, mobile/desktop va Telegram WebView’da bajariladi. Haqiqiy katalog, support aloqa, ish vaqti va checkout readiness Phase 2 admin sozlamalari bilan owner tasdig‘idan o‘tadi. Build, migration va deployed image’ni bir xil SHA bilan tekshirmasdan vitrina to‘liq deb e’lon qilinmaydi.
