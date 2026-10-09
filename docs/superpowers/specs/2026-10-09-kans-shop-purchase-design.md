# Kans Shop xarid jarayonini yaxshilash dizayni

Kans Shop bitta do‘kon bo‘lib qoladi. Maqsad — Telegram Mini App va oddiy brauzerda ishonchli xarid qilish, keyin shu tizim ustiga web admin va yaxshilangan vitrina qurish. Safran va Tezqurbot qulaylik uchun namunadir; Kans Shop o‘z mahsulotlari, bot va ma’lumotlar bazasini saqlaydi.

Bu hujjat birinchi bosqich — savat, mijoz kirishi, checkout va to‘lov cheki — dizaynidir. Foydalanuvchi yozma dizaynni va uning implementatsiya rejasini 2026-10-09 kuni tasdiqlagan. Foydalanuvchining yangi ketma-ketlik talabi bo‘yicha avval web admin va vitrina bosqichlari ham kelishiladi, keyin barcha bosqichlar avtonom bajariladi.

## Kelishilgan maqsad va bosqichlar

| Bosqich | Natija | Ushbu hujjatdagi scope |
| --- | --- | --- |
| 1. Xarid jarayoni | Ishlaydigan savat, tushunarli kirish, izchil checkout va yopiq chek yuborish | Batafsil dizayn |
| 2. Web admin | Mahsulotlar va rasmlar, kategoriyalar, buyurtmalar, sozlamalar, rollar va amallar tarixi | Keyingi alohida dizayn va reja |
| 3. Vitrina | Mobil va desktop ko‘rinishlari, qidiruv va sahifalash, til almashtirish, kabinet va buyurtma holatlari | Keyingi alohida dizayn va reja |

Avvalgi `docs/ASSUMPTIONS.md`dagi web adminni bekor qilish qarorini foydalanuvchining yangi talabi almashtiradi. Birinchi bosqich tugashi butun marketplace yangilanishi tugaganini anglatmaydi.

## Joriy holat va muammo

2026-10-09 kuni Netcup’da `kans-api` va `kans-frontend` healthy holatda bo‘lgan. Sayt `https://kans.standart-eko.uz`, sozlangan bot `@kansshopbot`. Image tag va GitHub `main` commit’i `16718babb4dba0b83d925f8b9bb09005e332f53f`; shu commit uchun CI va deploy muvaffaqiyatli tugagan. Repo `muradjanov-dev/kans-shop`. Rasmdagi `kans-shop-tizim` nomi joriy GitHub hisobidan topilmadi; boshqa repo bilan avtomatik birlashtirish qilinmaydi.

Production loglarda `POST /api/v1/cart/items` uch marta va `GET /api/v1/cart` ikki marta 500 bilan tugagan. `CartOut.items.0.product.images` serializatsiyasida `MissingGreenlet` qayd etilgan. `cart_repository.get_active_cart()` savatdagi mahsulotlarni yuklaydi, lekin ularning rasmlarini yuklamaydi. Telegram auth uchun 200 javobi ham bor: savat nosozligini faqat login muammosi bilan izohlash mumkin emas.

Oddiy brauzerda frontend Telegram `initData` bo‘lmasa qo‘shish tugmasini o‘chiradi, lekin kirish yo‘lini ko‘rsatmaydi. Savat mutatsiyalaridagi xatolar ham ko‘rsatilmaydi. Karta orqali o‘tkazish tanlovi mavjud, ammo frontendda rekvizitlar va chek yuklash yo‘q. Public settings tekshiruvida do‘kon qiymatlari `null`, online providerlar ro‘yxati esa bo‘sh bo‘lgan.

Backend xizmatlari, bot admini va ko‘plab admin API’lari mavjud. React ilovasida web admin sahifalari hali yo‘q. Birinchi bosqich mavjud FastAPI, aiogram, SQLAlchemy, PostgreSQL, Redis va React stack’idan foydalanadi.

## Ko‘rib chiqiladigan asosiy tanlov

Tavsiya — barcha xaridlarni Telegram hisobiga bog‘lash. Mehmon katalog va mahsulot sahifalarini ko‘radi; birinchi qo‘shishdan oldin Telegram orqali kiradi. Kirish davomida faqat bosilgan mahsulot va miqdor saqlanadi. Brauzer va Mini App kirgandan keyin aynan bitta server savati va buyurtmalar tarixini ishlatadi.

Bu tanlov mavjud foydalanuvchi modelini saqlaydi va mehmon savatini birlashtirish protokolini talab qilmaydi. To‘liq mehmon savati yoki Telegram hisobsiz buyurtma ushbu bosqichga kirmaydi. Foydalanuvchi shu farazni yozma dizayn bilan birga ko‘rib chiqadi.

## Modul chegaralari

| Modul | Vazifa va interfeys | Bog‘liqlik |
| --- | --- | --- |
| Mijoz autentifikatsiyasi | Mini App `initData` yoki bot bergan mijoz kodi orqali mavjud `User` va token juftligini qaytaradi | Telegram identity, Redis, user repository, joriy JWT helpers |
| Savat xizmati | Qo‘shish, o‘zgartirish, olib tashlash va tozalash; to‘liq serializatsiya qilinadigan savat qaytaradi | Cart va product repository’lari |
| Xarid sozlamalari | Do‘kon ochiqligi, narxga ta’sir qiluvchi sozlamalar va to‘lov usullarining tayyorligini tekshiradi | Setting repository va provider konfiguratsiyasi |
| Buyurtma xizmati | Savat va zaxirani tekshiradi, yagona buyurtma yaratadi, takror so‘rov va status o‘zgarishlarini boshqaradi | PostgreSQL transaction, cart/product/order repository’lari |
| Chek xizmati | Faylni tekshiradi, xususiy saqlaydi va faqat ruxsatli mijoz/admin uchun o‘qiydi | Fayl storage, order ownership va admin role checks |
| Frontend xarid oqimi | Kirish, savat, checkout, chek va xatodan tiklanish holatlarini ko‘rsatadi | Shu REST API va TanStack Query |

Biznes qoidalari `backend/app/services/`da qoladi. Bot va API alohida hisoblash, narx yoki stock qoidalarini yaratmaydi. Repository’lar SQL va eager loading’ni bajaradi; UI muvaffaqiyatni server javobi asosida ko‘rsatadi.

## Kirish va sessiya oqimi

Mini App joriy HMAC bilan tekshirilgan `initData` orqali avtomatik kiradi. Auth muvaffaqiyatsiz bo‘lsa katalog ochiq qoladi, lekin xarid tugmasi kirish holati va qayta urinishni tushuntiradi. SDK kech yuklanishi, tarmoq xatosi va haqiqiy brauzer holati ajratiladi.

Oddiy brauzerda «Savatga qo‘shish» kirish oynasini ochadi. U `@kansshopbot`ning shaxsiy chatiga olib boradi; mijoz `/web_login` buyrug‘i bilan bir martalik kod oladi va uni saytda kiritadi. Brauzer Telegram ID yoki rol yuborib hisob tanlay olmaydi.

Mijoz kodining qoidalari:

- Kod sakkizta raqamdan iborat, kriptografik random generator bilan yaratiladi va 5 daqiqa yashaydi. Redis’da collision bo‘lsa boshqa kod yaratiladi; mavjud kod ustiga yozilmaydi.
- Kod faqat shaxsiy bot chatida beriladi. Bitta foydalanuvchi uchun yangi kod oldingisini bekor qiladi; berish tezligi bir foydalanuvchiga daqiqasiga bir marta cheklanadi.
- Yangi `POST /api/v1/auth/customer/code` mijoz kodini almashtiradi. Mijoz va admin kodlari alohida namespace va endpointlardan foydalanadi. Kod serverda atomik olinib o‘chiriladi; ikki parallel exchange faqat bitta muvaffaqiyat beradi.
- Exchange uchun bir ishonchli client IP’dan 5 daqiqada 5 ta urinish ruxsat etiladi. Proxy manzili barcha xaridorlarni bitta mijozga aylantirmasligi kerak; forwarded IP faqat mavjud ishonchli reverse proxy’dan qabul qilinadi.
- Noto‘g‘ri, ishlatilgan va muddati o‘tgan kod bir xil tushunarli xato qaytaradi. Kodlar, JWT va `initData` loglarga chiqarilmaydi.
- Kod mavjud Telegram foydalanuvchisini bildiradi; admin ruxsati avvalgidek faol database roli orqali tekshiriladi. Kod endpointi mijozdan admin flag qabul qilmaydi.

Mavjud access/refresh token juftligi saqlanadi: 30 daqiqalik access va 7 kunlik refresh, konfiguratsiya boshqacha belgilangan bo‘lsa o‘sha qiymatlar. Bir nechta parallel 401 uchun bitta refresh bajariladi; har so‘rov ko‘pi bilan bir marta qayta yuboriladi. Refresh tugasa UI qayta kirishni taklif qiladi. Chiqish brauzer tokenlari va hisobga tegishli query cache’ni tozalaydi; server savatini o‘chirmaydi. Boshqa hisobga kirganda oldingi hisobning savati yoki buyurtmalari ko‘rsatilmaydi.

Kirish davomida bitta pending add `{productId, quantity, origin, mutationKey}` shu tabning session storage’ida saqlanadi. Unda narx, token yoki shaxsiy ma’lumot bo‘lmaydi. Oyna yopilsa yoki mijoz orqaga qaytsa pending intent bekor qilinadi va oldingi mahsulot/qidiruv sahifasi saqlanadi. Kirish oynasi ochiq paytda ikkinchi Add bajarilmaydi; birinchi intent yashirincha almashtirilmaydi. Kirish muvaffaqiyatidan keyin so‘rov avtomatik bir marta yuboriladi.

Add so‘rovi UUID `Idempotency-Key` bilan yuboriladi. Alohida `cart_mutations` jadvali `(user_id, mutation_key)` unique constraint, request fingerprint va created time’ni saqlaydi; user/cart lock ostida delta va marker bir transaction’da yoziladi. Bir xil key/payload replay miqdorni yana oshirmaydi va joriy savatni qaytaradi; boshqa payload conflict beradi. Javobi noma’lum bo‘lsa intent va key saqlanadi, UI qayta urinish taklif qiladi va aynan shu key qayta ishlatiladi. Stock/validation rad javobidan keyin miqdorni tuzatish yangi intent/key yaratadi. Pending intent 24 soatdan keyin bekor bo‘ladi; mutation markerlari kamida 7 kun saqlanadi. Shu limitlar expiry testida tekshiriladi. Bu mexanizm login’dan keyingi add hamda logged-in quick add uchun bir xil ishlaydi; mehmon savati yaratmaydi.

Shu bosqichda mavjud `/admin_login` ham shaxsiy chat bilan cheklanadi va kod exchange atomik qilinadi. To‘liq web admin sessiyasi, token revoke va admin audit UI ikkinchi bosqichning alohida dizayniga kiradi.

## Savatning kutiladigan xatti harakati

`CartOut` formati saqlanadi. GET, add, update, remove va clear javoblari mahsulot rasmlarini ham to‘liq yuklaydi; serializatsiya paytida yashirin async database so‘rovi bajarilmaydi. Test yangi DB sessiyasida saqlangan savatni olishi shart; faqat bir sessiyadagi service obyektini tekshirish yetarli emas.

Katalogdagi quick add sahifani o‘zgartirmaydi: muvaffaqiyat belgisi va savat hisoblagichi yangilanadi. Mahsulot sahifasidagi qo‘shish muvaffaqiyatli javobdan keyin savatga olib boradi. Har ikkisi loading holatini va lokalizatsiya qilingan xatoni ko‘rsatadi. Server muvaffaqiyati olinmasdan «qo‘shildi» ko‘rsatilmaydi.

Boshlang‘ich miqdor `min_order_qty`dan boshlanadi. UI miqdorni minimum va mavjud stock bilan cheklaydi; server qoidalari baribir yakuniy tekshiruvni bajaradi. Add delta hisoblanadi, update esa absolut miqdor. Update uchun minimumdan past musbat miqdor rad etiladi, nol olib tashlashni bildiradi. Har qanday xatoda server savati va boshqa mahsulotlar saqlanadi.

API 401/403, stock conflict, 422, 429 va tarmoq/500 xatolariga mos harakat ko‘rsatiladi: qayta kirish, ruxsat tushuntirishi, miqdorni tuzatish, maydonni tuzatish yoki qayta urinish. Texnik stack trace mijozga chiqarilmaydi.

## Sozlamalar va checkout

Narxga ta’sir qiladigan sozlamalar bitta typed loader’dan olinadi. `delivery_fee`, `free_delivery_from`, `min_order_amount` manfiy bo‘lmagan son bo‘lishi kerak. Noldan foydalanish aniq bepul yoki cheklov yo‘q qiymatidir; `null`, yo‘q va noto‘g‘ri qiymat nolga aylantirilmaydi. `is_shop_open` haqiqiy boolean bo‘ladi.

Yangi `POST /api/v1/orders/quote` checkout turini va tanlangan to‘lov usulini qabul qilib, server hisoblagan subtotal, delivery fee, total, mavjud usullar, checkout readiness va `quote_fingerprint`ni qaytaradi. Fingerprint ID bo‘yicha tartiblangan mahsulot ID/miqdor/live price/active holati, order type, payment method, jami va tegishli do‘kon sozlamalarining canonical snapshot’idan olinadi. Total bir xil qolib cart mazmuni o‘zgarsa ham fingerprint o‘zgaradi. Stock har doim checkout paytida alohida qayta tekshiriladi. Bu static route `/{order_id}`dan oldin ro‘yxatdan o‘tkaziladi. UI pulni API decimal qiymatlari bilan ko‘rsatadi; uning hisoblashlari narx uchun manba bo‘lmaydi.

Do‘kon yopiq yoki kerakli sozlama yetishmasa katalog, savat va oldingi buyurtmalar ochiq qoladi, yangi checkout esa tushunarli xabar bilan to‘xtaydi. Yetkazish uchun uchta narx sozlamasi, pickup uchun minimum sozlamasi, barcha turlar uchun do‘kon ochiqligi tekshiriladi. Preorder minimum summadan ozod va narx sozlamalari yo‘qligi unga to‘siq bo‘lmaydi, ammo do‘kon yopiq bo‘lsa yangi so‘rov ham yaratilmaydi. Demo seed production’dagi narx, karta yoki mavjud katalogni almashtirmaydi.

Checkout ism, O‘zbekiston telefon raqami va delivery uchun manzilni tekshiradi. Maydon xatolari blur yoki yuborishga urinishda ko‘rinadi; o‘chiq submit tugmasi yagona tushuntirish bo‘lib qolmaydi. Bu bosqich manzilni matn bilan qabul qiladi; xarita, saqlangan manzillar va to‘liq kabinet uchinchi bosqichga qoladi.

To‘lov qoidalari:

| Usul | Qachon taklif qilinadi | Keyingi harakat |
| --- | --- | --- |
| Cash | Do‘kon checkout uchun tayyor bo‘lsa | Buyurtma yaratiladi, admin joriy tartibda boshqaradi |
| Card transfer | Haqiqiy `card_number` va `card_holder` sozlangan bo‘lsa | Buyurtma, uning summasi va rekvizitlari ko‘rsatiladi; mijoz chek yuklaydi |
| Click va Payme | Barcha kerakli merchant va secret qiymatlari mavjud, integration owner tomonidan tekshirilgan bo‘lsa | Mavjud provider oqimi; muvaffaqiyatsiz link so‘rovi shu buyurtmada qayta uriniladi |
| Paynet | Bu bosqichda taklif qilinmaydi | Haqiqiy merchant protokoli uchun keyingi alohida ish kerak |
| Tender | Savatdagi kamida bitta mahsulotda lot URL bo‘lsa | Lot havolalari va havolasi yetishmaydigan mahsulotlar mavjud service qoidasi bilan ko‘rsatiladi |
| Preorder | Buyurtma turi sifatida mavjud | Menejer qayta bog‘lanadi; to‘lov tanlash, manzil, delivery fee va minimum gate yo‘q. Mavjud cash enum qiymati texnik default bo‘lib qoladi, pul undirilganini bildirmaydi |

Backend tanlangan usulning mavjudligini qayta tekshiradi. Brauzerda yashirilgan provider’ni API orqali tanlash uni yoqmaydi. Online credential kiritish, provider yoqish va real to‘lov qilish bu dizayn tasdig‘ining o‘zi bilan bajarilmaydi.

## Buyurtma yaratish va takror so‘rov

Buyurtma yaratish uchun yangi frontend `Idempotency-Key` header, `expected_total`, `expected_quote` va `purchase_contract_version: 1`ni yuboradi. `expected_quote` oxirgi `quote_fingerprint` qiymatidir. Tasdiqlash boshlanganida UUID yaratiladi; javob yo‘qolsa shu key saqlanadi. Forma mazmuni yoki quote tasdiqlangan holda o‘zgarsa yangi key yaratiladi. Bot confirmation state ham bitta stable key va mijoz ko‘rgan quote fingerprint’ni saqlaydi.

Orders jadvaliga nullable checkout key va request fingerprint qo‘shiladi; `(user_id, checkout_key)` unique bo‘ladi. Mavjud buyurtmalar o‘zgarmaydi. HTTP key UUID satri sifatida validatsiya qilinadi. Request fingerprint checkout maydonlari, expected quote va expected totalning normalizatsiya qilingan mazmunidan olinadi; foydalanuvchi har doim server sessiyasidan aniqlanadi.

Bir xil key va payload qayta kelganda original buyurtma qaytariladi; savat ikkinchi marta bo‘shatilmaydi, stock ikkinchi marta kamaymaydi va yangi buyurtma notification’i qayta boshlanmaydi. Bir xil key bilan boshqa payload `409 IDEMPOTENCY_CONFLICT` qaytaradi. Key boshqa foydalanuvchining buyurtmasini ochmaydi. Birinchi yaratilish 201, replay 200 qaytaradi.

Version 1 HTTP checkout key, expected total va expected quote’ni majburiy qiladi. Versiyasiz eski frontend uchun bu maydonlar optional qoladi; legacy cash/tender checkout cart lock va stock checks’dan o‘tadi, ammo durable replay yoki oldingi quote tasdig‘i kafolatiga ega emas. Legacy HTTP card transfer esa DB yozuvidan oldin `409 CLIENT_UPDATE_REQUIRED` bilan rad etiladi va sahifani yangilashni tushuntiradi: eski bundle rekvizit/chek oqimini bajara olmaydi. Bot direct service adapter’i legacy frontend hisoblanmaydi. Yangi UI version 1 yuborishi va invalid/missing kontraktning rad etilishi test qilinadi. Deploy acceptance cached eski bundle’ni ham tekshiradi.

Transaction ichida user row, uning faol cart row’i va product row’lari shu tartibda lock qilinadi; productlar ID bo‘yicha olinadi. Barcha bot/API cart mutatsiyalari va checkout bir xil user/cart lock tartibidan foydalanadi. Lock’dan keyin cart qayta yuklanadi va idempotency natijasi qayta tekshiriladi. So‘ng mavjudlik, stock, sozlamalar, usul va expected total tekshiriladi.

Expected total yoki expected quote joriy snapshot’dan farq qilsa `409 QUOTE_CHANGED` va yangi quote qaytariladi; buyurtma yaratish va stock kamaytirish bajarilmaydi. Mijoz yangilangan tarkib/summani ko‘rib qayta tasdiqlaydi. Bir xil checkout key replay’i joriy bo‘sh cart bilan quote solishtirishdan oldin aniqlanadi va original order’ni qaytaradi. Muvaffaqiyatda order va item snapshot’lari, stock/sold count, initial status history va cart clear bitta transaction’da saqlanadi. Istalgan bosqichdagi xato ularning hammasini rollback qiladi.

Transaction chegarasini request yoki bot update orchestration’i boshqaradi; service ichida mavjud transaction ustiga yangi `begin()` qo‘shilmaydi. Javob commit’dan keyin muvaffaqiyat sifatida beriladi. Telegram xabarlari commit’dan keyin yuboriladi; xabar yuborish xatosi saqlangan buyurtmani rollback qilmaydi va xarid muvaffaqiyatini 500ga aylantirmaydi. Xabar xatosi order ID bilan qayd etiladi va admin mavjud buyurtmalar ro‘yxatidan uni ko‘radi. Restart’dan keyingi durable notification queue ikkinchi bosqichda dizayn qilinadi; Telegram yetkazilishi uchun exactly-once kafolati berilmaydi.

Order status o‘zgarishi va cancel order row lock’dan keyin joriy holatni qayta tekshiradi. Ikki admin parallel bekor qilsa bitta cancellation history yozuvi va bitta stock/sold count qaytarilishi bo‘ladi. Ikkinchi harakat «allaqachon bajarilgan» javobini oladi. Mavjud status ketma-ketligi saqlanadi. Paid order cancel pul qaytarilganini anglatmaydi; avtomatik refund bu scope’da yo‘q.

Mavjud Click/Payme callback oqimlari provider protokolini almashtirmasdan order row, keyin shu provider transaction row’ini lock qilib tekshiradi. Provider, order, summa, payable holat va transaction association mos bo‘lishi kerak. Aynan bir transaction’ning valid takror callback’i idempotent success; boshqa transaction allaqachon paid order’ni qayta to‘lay olmaydi. Cancelled/completed order uchun yangi payment qabul qilinmaydi. HTTP pay-link endpoint ham order method/provider mosligi va unpaid non-terminal holatni tekshiradi. Bu tekshiruvlar fake callback testlari bilan bajariladi; live provider yoqilmaydi va Paynet placeholder oqimi yangi to‘lov uchun ishlatilmaydi.

## Karta rekvizitlari va chek

Card transfer order yaratilganda karta raqami va egasi order payment instructions snapshot’iga saqlanadi. Keyingi sozlama o‘zgarishi oldingi unpaid buyurtmaning ko‘rsatilgan rekvizitlarini almashtirmaydi. Mavjud order’da snapshot bo‘lmasa joriy rekvizit yashirincha yangi snapshot sifatida berilmaydi; «Rekvizitni admin bilan aniqlashtiring» xabari va mavjud support yo‘li ko‘rsatiladi.

Order detail’da summa, karta ma’lumotlari, nusxalash tugmasi va chek yuklash bor. JPEG, PNG, WebP va PDF, ko‘pi bilan 5 MiB qabul qilinadi. Fayl read vaqtida limit bilan tekshiriladi; declared MIME yetarli emas, content ham ruxsatli turga mos bo‘ladi. Upload xatosida buyurtma saqlanadi va yana uriniladi.

Faqat order egasi o‘zining unpaid, non-terminal card transfer order’iga chek yuboradi. Awaiting review holatida chek almashtirish mumkin. Paid, completed va cancelled order, shuningdek cash/tender/online usullar uchun upload rad etiladi. Eligibility lock’dan keyin qayta tekshiriladi. Chek yuklash `receipt_uploaded`ni bildiradi, `paid`ni emas. Mavjud admin tasdiqlash qoidasi alohida amal bo‘lib qoladi.

Manual transfer uchun alohida «To‘lovni tasdiqlash» bot admin amali va `POST /api/v1/admin/orders/{order_id}/payment/accept` qo‘shiladi. Joriy buyurtma boshqarish huquqiga ega faol admin receipt_uploaded card transfer order’ini qabul qiladi. Har upload `receipt_version`ni oshiradi; accept ko‘rilgan version’ni yuboradi va stale versiya 409 beradi. Order lock ostida `payment_status=paid`, `payment_reviewed_by_admin_id` va `payment_reviewed_at` saqlanadi. Bir xil version qayta tasdiqlansa o‘sha natija qaytadi; yangi payment/history yozilmaydi. Bu amal order status’ini o‘zgartirmaydi: «Buyurtmani tasdiqlash» alohida mavjud amal bo‘lib qoladi. Chek yo‘q, boshqa method yoki terminal order qabul qilinmaydi. Paid holatni ortga qaytarish va refund ushbu bosqichga kirmaydi.

Cheklar public `/media` ostida tarqatilmaydi. `GET /api/v1/orders/{order_id}/receipt` owner yoki hozir faol, buyurtma ko‘rishga ruxsatli admin uchun faylni qaytaradi; anonymous va boshqa mijozga rad javobi beradi. Javob `Cache-Control: private, no-store` bilan qaytadi. Frontend bearer-authenticated fetch orqali ko‘rsatadi; token URL query’ga yozilmaydi.

Yangi private storage public product media’dan ajratiladi. Netcup’da Kans Shop’ga tegishli alohida private media volume `/app/private_media`ga mount qilinadi; public `MEDIA_ROOT` ostida chek nusxasi qolmaydi. Eski fayllar backup’dan keyin private volume’ga ko‘chiriladi va barcha order reference’lari uchun read resolver tekshiriladi. Faqat har bir fayl yangi storage’da tasdiqlangandan keyin uning public nusxasi olib tashlanadi; shu cutover vaqtida public receipt route yopiq bo‘ladi.

Eski `/media/receipts/*` yo‘li backend va mavjud nginx yo‘lida yopiladi. `receipt_url` eski clientlarni buzmaslik uchun maydon sifatida qoladi, lekin yopilgan legacy URL qayta ochilmaydi; yangi UI authenticated receipt endpoint’dan foydalanadi. Eski app image’iga rollback qilinsa ham private volume va fayllarning public root tashqarisidagi joylashuvi saqlanadi. Legacy image authenticated read’ni qo‘llamasligi mumkin, ammo cheklar qayta public bo‘lmaydi. File migration’dan keyin eski public nusxani qayta tiklash rollback usuli hisoblanmaydi.

Botdan kelgan chek va HTTP upload bitta validation/storage service’dan foydalanadi. Bot adminning ko‘rish amali Telegram `file_id` bo‘lsa uni, aks holda private faylni serverdan olib yuboradi. Shuning uchun web’dan yuklangan chek ham bot adminida ko‘rinadi. File replacement vaqtida eski fayl yangi fayl va DB reference saqlanmaguncha o‘chirilmaydi.

## API o‘zgarishlarining chegarasi

Mavjud catalog, cart va order URL’lari saqlanadi. Qo‘shiladigan yuzalar: mijoz kodi exchange, checkout quote, authenticated receipt read, manual payment accept, order instructions snapshot va add/checkout replay metadata. Alembic migration `cart_mutations`ni, order checkout metadata’sini, payment instructions snapshot’ini, receipt version va payment reviewer/time’ni qo‘shadi. Yangi error code’lar mavjud `{error: {code, message, details}}` shaklidan foydalanadi. Public settings’ga readiness va sabablar qo‘shilishi additive bo‘ladi; secret qiymatlar hech qachon public javobga kirmaydi.

DB o‘zgarishlari Alembic migration bilan bajariladi. Existing order, user, category, product, cart va payment ma’lumotlari saqlanadi. Ushbu bosqich yangi sotuvchi modeli, guest user, web admin UI, yangi payment gateway yoki ommaviy katalog importini yaratmaydi.

## Qabul qilish mezonlari

| Holat | Tekshiriladigan natija |
| --- | --- |
| Saqlangan rasmlik savat | Yangi sessiyada GET/add/update/remove/clear valid `CartOut` qaytaradi; `MissingGreenlet` yo‘q |
| Anonymous brauzer | Katalog ochiladi, Add kirish oynasini ochadi, pending mahsulot bir marta qo‘shiladi; cancel/reopen va ikkinchi Add intent’ni yashirincha almashtirmaydi |
| Telegram Mini App | Avtomatik verified login, qo‘shish va umumiy server savati ishlaydi |
| Kod va sessiya | Private chat, expiry, collision, reuse, parallel exchange, rate limit va expired refresh holatlari tekshiriladi |
| Hisob almashtirish | Bir hisobning cache/savati/tarixi boshqa hisobga ko‘rinmaydi |
| Miqdor va xatolar | Minimum va stock tekshiriladi; 401/403/409/422/429/500 va offline holat ko‘rinadi; lost add response + same key retry miqdorni ikki marta oshirmaydi |
| Sozlamalar | Missing/null/malformed/negative, shop closed va explicit zero qiymatlar ajratiladi |
| Quote va to‘lov | Server jami ko‘rsatiladi; teng jami bilan o‘zgargan cart ham qayta tasdiqlanadi; unavailable provider rad etiladi; preorder/tender qoidalari saqlanadi |
| Parallel checkout | Bir userning bir cart’i ikki order bermaydi; ikki user oxirgi stock uchun kurashganda ortiqcha sotilmaydi |
| Replay va rollback | Bir xil key bitta order/stock decrement beradi; boshqa payload conflict; xatoda barcha DB writes rollback |
| Parallel status/cancel | Bitta state change/history, stock bir marta qaytariladi |
| Card transfer | Snapshot, upload, stale receipt version, alohida payment accept va web chekining bot adminida ko‘rinishi ishlaydi; legacy HTTP client reload xabari oladi |
| Online callback | Duplicate transaction bitta payment beradi; wrong provider/order/amount, terminal order va ikkinchi successful transaction rad etiladi |
| Receipt privacy | Anonymous, boshqa user va inactive admin faylni ololmaydi; public legacy URL yopiq; hajm/type/state cheklovi ishlaydi |
| Notification xatosi | Telegram yuborish xatosi committed order’ni bekor qilmaydi va checkout retry yangi order yaratmaydi |

Backend HTTP testlari fake bot va alohida disposable PostgreSQL/Redis bilan ishlaydi. Ayniqsa API serialization va concurrency haqiqiy database sessiyalarida tekshiriladi. `backend/tests/conftest.py` test bazasi schema’sini drop/create qiladi; production bazasi bu testlar uchun ishlatilmaydi.

Frontend uchun auth, refresh, mutation feedback va checkout retry testlari hamda brauzerda asosiy xarid journey’si qo‘shiladi. Telegram mock brauzer testi haqiqiy Telegram qurilmasidagi acceptance o‘rnini bosmaydi. Haqiqiy qurilmada yakuniy tekshiruv alohida test bot/katalog bilan bajariladi.

## Release shartlari

Implementatsiya mavjud application code bilan mos `origin/main` bazasidan boshlanadi. Joriy lokal `codex/agent-context` branch’ini yangi release bazasi deb qabul qilish mumkin emas; audit vaqtida application diff bo‘lmagan, ammo branch va hujjatlar farq qiladi.

Backend `ruff check app tests`, `black --check app tests`, `mypy app`, `pytest -q`; frontend `npm ci`, `npm run typecheck`, `npm run build` va yangi journey testlari o‘tadi. Migration disposable bazadagi eski schema/data nusxasida tekshiriladi. Test credential’lari synthetic bo‘ladi; production token va real mijoz order’i testga ishlatilmaydi.

Owner 2026-10-09 kuni haqiqiy delivery fee, free-delivery threshold, minimum va dastlabki to‘lov usullarini keyin belgilashini aytdi. Bu qiymatlar tayyor bo‘lmagani software implementatsiyasi yoki konfiguratsiya holati aniq ko‘rsatilgan release’ni to‘xtatmaydi. Public sozlamalar `null` bo‘lib qolsa katalog, savat va tarix ishlaydi, yangi checkout esa yopiq turadi; owner ularni keyin web admindan kiritadi. Sozlamalar uchun taxminiy narx yoki demo karta kiritilmaydi va online provider avtomatik yoqilmaydi.

`AGENTS.md` talabiga ko‘ra payment, prices, roles, migrations, secrets va CI/deploy o‘zgarishlari release oldidan owner review’dan o‘tadi. Spec yoki implementatsiya rejasi tasdig‘i shu release review’ning o‘rnini bosmaydi. Main orqali mavjud Netcup workflow va commit SHA image’lari ishlatiladi; saytlarni qo‘lda qayta deploy qilish yoki umumiy stack’ni qayta yaratish bu scope’da yo‘q.

Shared PostgreSQL/Redis, Kans product media volume va boshqa xizmatlar saqlanadi. Kans Shop compose’iga private media mount qo‘shish owner release review’iga kiradi; umumiy network/proxy yoki boshqa stack’lar o‘zgarmaydi. Release oldidan database/private media backup’i, migration compatibility va eski image bilan receipt privacy cutover tekshiriladi. Oxirgi ishlayotgan app image’lari `16718babb4dba0b83d925f8b9bb09005e332f53f`; yangi migration oldingi image bilan mosligi va private fayllar re-exposure qilinmasligi tekshirilmasa image rollback xavfsiz deb e’lon qilinmaydi.

Yangi release dalili: aynan deploy qilingan SHA uchun muvaffaqiyatli GitHub CI/deploy, healthy konteynerlar, HTTPS catalog/health, registered webhook va test muhitidagi to‘liq xarid acceptance. Production’da real order yaratish yoki haqiqiy to‘lov qilish verification usuli bo‘lmaydi.

## Koddagi tayanch nuqtalar

- `backend/app/db/repositories/cart_repository.py` va `backend/app/api/schemas/cart.py`: tasdiqlangan savat serializatsiyasi muammosi.
- `frontend/src/hooks/useTelegramAuth.ts`, `frontend/src/lib/api.ts`, `frontend/src/store/auth.ts`: auth, refresh va hisob cache’i.
- `frontend/src/components/ProductCard.tsx`, `frontend/src/pages/ProductPage.tsx`, `frontend/src/hooks/queries.ts`: pending add va mutation feedback.
- `backend/app/api/v1/auth.py`, `backend/app/bot/handlers/admin/auth.py`: mavjud token/kod infratuzilmasi.
- `backend/app/services/order_service.py`, `backend/app/db/repositories/order_repository.py`: checkout, locking, status va cancellation.
- `backend/app/services/payment_service.py`, `backend/app/api/v1/settings.py`: usullar va konfiguratsiya tekshiruvi.
- `backend/app/api/v1/orders.py`, `backend/app/core/uploads.py`, `backend/app/bot/handlers/user/receipt_redirect.py`: chek upload va access.
- `frontend/src/pages/CheckoutPage.tsx`, `frontend/src/pages/OrderDetailPage.tsx`: server quote, rekvizit va payment recovery UI.
- `docs/ASSUMPTIONS.md`, `AGENTS.md`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`: saqlanadigan biznes va release qoidalari.
