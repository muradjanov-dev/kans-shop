# Kans Shop web admin dizayni

## Hujjat holati

Bu ikkinchi bosqichning yozma dizayn taklifi. Foydalanuvchi web adminning botdagi admin ishlarini to‘liq qamrab olishini, uchinchi bosqichdagi vitrina ishlarini ham alohida kelishishni tasdiqladi. Birinchi bosqich xarid dizayni va rejasi alohida tasdiqlangan. Owner ushbu yozma dizaynni 2026-10-09 kuni tasdiqladi va qolgan rejalarni yozib, qayta to‘xtamasdan implementatsiyaga o‘tishni so‘radi.

## Maqsad va chegaralar

Kans Shop bitta kanselyariya do‘koni bo‘lib qoladi. Shu React ilovasida responsive `/admin` qismi yaratiladi; u mavjud PostgreSQL, bot va FastAPI xizmatlaridan foydalanadi. Web admin xodimlarga buyurtma, katalog va do‘kon ishlarini brauzerdan boshqarish imkonini beradi. Telegram bot admin konsoli ham ishlashda davom etadi; bot va web bir xil biznes qoidalarini bajaradi.

Ushbu bosqich botdagi kundalik admin imkoniyatlarining parity’sini ta’minlaydi: buyurtmalar, mahsulot/kategoriya/rasmlar, foydalanuvchilar, statistika va XLSX eksport, sozlamalar, xodimlar/rollar, traffic source’lar va broadcast’lar. Mijoz vitrinasining umumiy mobil/desktop qayta dizayni uchinchi bosqich; bu yerda faqat admin sahifalari responsive qilinadi.

## Joriy holat

Frontend `App.tsx`da faqat mijoz sahifalari bor. FastAPI’da categories, products, orders, users, stats va broadcasts admin routerlari mavjud. Settings, admin-team va source management REST sirtlari yo‘q. Botda bularning barchasi bor. Bot admin handlerlari va bir necha REST handlerlari repository’larni bevosita chaqiradi; yangi admin qoidalari `app/services/`dagi umumiy modullar orqali bajariladi.

Botdagi role modeli: `superadmin`, `manager`, `operator`. Order ko‘rish va statusni boshqarish barcha faol rollarga ochiq. Product/category, settings, user blocking, source va broadcast boshqaruvi manager/superadmin; team boshqaruvi superadmin-only. Bot statistikani barcha faol adminlarga ko‘rsatadi. REST stats hozir manager/superadmin bilan cheklangan; yangi web/API qoidasi botdagi operator stats ko‘rish huquqiga moslanadi. Hozirgi `ADMIN_IDS` superadmin bootstrap’i faqat seed script’da yangi qator qo‘shadi; deploy vaqtida mavjud inactive yoki demote qilingan adminni qayta yoqmaydi. Web team boshqaruvi seed/env qiymatlarini o‘zgartirmaydi.

Statistikada `orders_count` davrda yaratilgan barcha orderlarni, jumladan cancelled’ni hisoblaydi. Mavjud API `revenue` maydoni cancelled bo‘lmagan orderlarning `total`ini payment status’dan qat’i nazar qo‘shadi; maydon API mosligi uchun qoladi, bot/web UI/XLSX esa “bekor qilinmagan buyurtmalar summasi” deb nomlaydi. Bu tushgan pul emas. “To‘lovi tasdiqlangan buyurtmalar summasi” `payment_status=paid` va `status != cancelled` orderlardan hisoblanadi; bu bank/kassa settlement hisobi emas. Avg check mavjud non-cancelled order count’ga bo‘linadi. `today` Asia/Tashkent’dagi bugungi 00:00 dan hozirgacha, `week` oxirgi 7 kun, `month` oxirgi 30 kun hisoblanadi; DB chegaralari UTCga aylantiriladi. Bot, REST va XLSX bir xil stats service va period boundary’dan foydalanadi.

Campaign source user’ning birinchi-touch `users.traffic_source_id` qiymatida saqlanadi, order qatorida emas. Campaign order count va order value shu source’ga biriktirilgan foydalanuvchilarning orderlaridan hisoblanadi; UI buni per-order yoki last-click attribution deb ko‘rsatmaydi. Yangi login, qayta kirish yoki keyingi campaign havolasi first-touch qiymatini almashtirmaydi.

## Asosiy arxitektura

React `/admin/*` route’lari customer route’lar bilan bitta frontend bundle’da qoladi, lekin admin auth bootstrap customer `useTelegramAuth` flow’ini ishga tushirmaydi. Web ekranlari `/api/v1/admin/*` bilan ishlaydi. Handler va routerlar HTTP/bot adapterlari bo‘ladi; validation, ruxsat, transaction va audit umumiy service’larda yashaydi.

Har bir mutation service actor’ni `admin_id` orqali oladi, shu transaction’da `admins` qatorini yangidan o‘qiydi va `is_active` hamda amaldagi rolni tekshiradi. Frontenddan kelgan role, `is_admin`, Telegram ID yoki permissions hech qachon vakolat bermaydi. Bot FSM’da xodim roli formani ochganidan keyin o‘zgarsa, final saqlash amali yangi rolni qayta tekshiradi.

Tavsiya etilgan umumiy modullar: `admin_catalog_service` mahsulot/kategoriya/rasm qoidalari; `store_settings_service` typed settings; `admin_team_service`; `customer_admin_service`; `traffic_source_service`; `broadcast_service`; `admin_audit_service`; `notification_outbox_service`. Mavjud `catalog_service`, `order_service`, `stats_service`, `payment_service`, `broadcast_service` bilan umumiy hisob-kitoblar bo‘lishilganda yangi nusxa qoida yaratilmaydi.

## Admin sessiyasi

### Login va cookie

Xodim avval botning shaxsiy chatida mavjud `/admin_login` buyrug‘idan bir martalik kod oladi. Birinchi bosqich kod berishni shaxsiy chat bilan cheklaydi va atomik iste’mol qiladi; admin code namespace mijoz `/web_login` kodidan alohida qoladi. Exchange oldidan server `Admin` qatori mavjud, faol ekanini tekshiradi.

Admin auth API: `POST /api/v1/auth/admin/code/exchange` JSON `{code}` bir martalik kodni atomik iste’mol qilib session yaratadi; `GET /api/v1/auth/admin/session` joriy admin, serverdagi vakolatlar va shu session’ning CSRF tokenini qaytaradi; `POST /api/v1/auth/admin/session/refresh` idle muddatni uzaytiradi; `POST /api/v1/auth/admin/logout` joriy sessiyani bekor qiladi; `POST /api/v1/auth/admin/logout-all` shu adminning barcha browser sessiyalarini bekor qiladi.

Session token kriptografik random 256-bit qiymat; DB’da faqat SHA-256 digest saqlanadi. CSRF token alohida random 256-bit nonce bo‘ladi, session davomida barqaror va shu session row’ida saqlanadi; exchange hamda authenticated `GET /session` response’da qaytariladi. CSRF tokenning o‘zi cookie o‘rniga login qila olmaydi; DB’dagi session cookie digest’idan asl cookie tiklanmaydi. `__Host-kans-admin` cookie `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Domain` ko‘rsatmasdan beriladi. Idle muddati 12 soat, mutlaq muddati 7 kun; refresh idle muddatni uzaytiradi, lekin cookie/CSRF tokenini aylantirmaydi va 7 kunlik chegarani uzaytirmaydi, shuning uchun parallel tablar bir-birining sessiyasini buzmaydi. Login kodi, session token va CSRF nonce loglanmaydi.

Code exchange `Content-Type: application/json` va `Origin` aynan `settings.webapp_url` bo‘lishini talab qiladi. Cookie-authenticated barcha unsafe request’lar shu exact Origin va `X-CSRF-Token`ni talab qiladi; exchange uchun session hali yo‘qligi sababli CSRF header talab qilinmaydi. Oddiy mutation’lar JSON, rasm upload endpointlari esa chegaralangan `multipart/form-data`ni qabul qiladi va CSRF/Origin’dan ozod qilinmaydi. Cross-origin credential ruxsati kengaytirilmaydi; refresh/logout session CSRF tokenini tekshiradi. Auth, session, private receipt va shaxsiy admin javoblari `Cache-Control: private, no-store` bilan keladi.

### Buyer JWT bilan moslik

Customer `/auth/telegram`, `/auth/customer/code`, `/cart`, `/orders` va boshqa buyer API’larining Bearer JWT kontrakti saqlanadi; customer Axios client access/refresh JWT’dan foydalanishda davom etadi. Admin frontend alohida `adminApi` ishlatib cookie va CSRF yuboradi. Admin endpointlar Bearer tokenni hech qachon zaxira login sifatida qabul qilmaydi; sessiyasiz eski admin JWT `401 ADMIN_SESSION_REQUIRED` oladi.

Phase 1’dagi atomic admin code issuer `POST /api/v1/auth/admin/code/exchange`ga ulanadi. Eski `/api/v1/auth/telegram/code` admin JWT exchange’i `410 ADMIN_SESSION_REQUIRED` qaytaradi; buyer token endpointlariga ta’sir qilmaydi. Barcha `/api/v1/admin/*` endpointlar cookie session talab qiladi va Bearer fallback’i yo‘q; oldindan chiqarilgan admin JWT admin API’ga kira olmaydi. `GET /api/v1/orders/{order_id}/receipt`da cookie principal faqat faol admin session orqali order-view ruxsatini oladi; Bearer principal esa faqat `user.id == order.user_id` bo‘lganda egasi sifatida o‘qiydi. Bearer’dagi `is_admin` claim yoki Telegram ID orqali role lookup qilib boshqa mijoz cheki ochilmaydi. `admins.auth_epoch` va `admin_sessions.auth_epoch` saqlanadi; roli o‘zgarishi, deactivation yoki removal epoch’ni oshiradi va faol sessiyalarni shu transaction’da revoke qiladi. Har admin request session digest, expiry, `revoked_at`, epoch, admin faol holati va live rolni tekshiradi. Admin endpointlar uchun legacy Bearer mosligi ataylab yo‘q; epoch cookie sessiyalarini ham revoke qiladi.

## Rollar va ruxsatlar

| Amal | Superadmin | Manager | Operator |
| --- | --- | --- | --- |
| Order ko‘rish, status/cancel, mijozga yozish | Ha | Ha | Ha |
| Phase 1 card-transfer receipt’ni qabul qilish | Ha | Ha | Ha; bu amaldagi order-admin permission’ini saqlaydi |
| Mahsulot, kategoriya, rasm, narx, qoldiq, lot URL | Ha | Ha | O‘qish yo‘q; operator order ishiga cheklanadi |
| Foydalanuvchini ko‘rish/block qilish | Ha | Ha | Yo‘q |
| Do‘kon sozlamasi, traffic source, broadcast | Ha | Ha | Yo‘q |
| Statistika va XLSX eksport | Ha | Ha | Ha, faqat o‘qish |
| Xodim/rol/sessiya boshqaruvi | Ha | Yo‘q | Yo‘q |
| Audit | Ha | Ha, operatsion yozuvlar | Faqat o‘zi ishlagan order yozuvlari |

`operator`ning stats ko‘rishi amaldagi bot xatti-harakatini saqlaydi va REST/web’da ham ishlaydi. Payment accept phase 1 rejasi bo‘yicha barcha faol order-admin rollariga ochiq; bu amal order status’ini o‘zgartirmaydi. Boshqa write’lar uchun manager/superadmin kerak.

## Admin ekranlari va API kontrakti

### Shell va umumiy holatlar

`/admin/login`, `/admin`, `/admin/orders`, `/admin/catalog`, `/admin/customers`, `/admin/reports`, `/admin/settings`, `/admin/team`, `/admin/sources`, `/admin/audit`, `/admin/broadcasts` route’lari bir xil admin shell, breadcrumbs, nav, loading/error/empty state va uz/ru til bilan ishlaydi. 360px mobil, planshet va desktop’da jadval kartaga yoki boshqariladigan gorizontal scroll’ga o‘tadi. Admin sahifasi `GET /auth/admin/session` muvaffaqiyatsiz bo‘lsa API ma’lumotini ko‘rsatmaydi.

### Buyurtmalar

Saqlanadi: `GET /api/v1/admin/orders`, `GET /api/v1/admin/orders/{id}`, `PATCH /api/v1/admin/orders/{id}/status`, phase1 `POST /api/v1/admin/orders/{id}/payment/accept`, private receipt read. Order list status, qidiruv, sana, pagination/filter’larni ko‘rsatadi; detail’da customer, item snapshot, to‘lov holati, status history, receipt/payment review history bor. `POST /api/v1/admin/orders/{id}/message` 1–4096 belgili matn va UUID replay key bilan shu order egasiga bir martalik Telegram xabarini queue’ga yozadi; client recipient Telegram ID tanlay olmaydi. Faqat operator/adminning aniq send amali uni boshlaydi, audit matn o‘rniga message ID qayd etadi. Status grafigi, order lock/cancel stock qoidasi va phase1 receipt/payment contract o‘zgarmaydi.

Phase 1’dagi `GET /api/v1/orders/{order_id}/receipt` yo‘li customer uchun owner Bearer JWT bilan ishlashda davom etadi; admin uchun shu faylni yangi cookie session bilan o‘qish qo‘shiladi. Bearer token faqat order egasi bo‘lgan `user.id` bilan mos kelsa ruxsat oladi; bearer’dagi admin claim/Telegram ID bilan admin qidiruvi qilib boshqa mijoz cheki berilmaydi. Cookie principal esa faol order-view admin bo‘lishi kerak. Har ikkala principal uchun `Cache-Control: private, no-store`, ownership/role tekshiruvi va private storage resolver bir xil bo‘ladi.

### Katalog va rasmlar

Mavjud `/admin/categories` va `/admin/products` CRUD route’lari saqlanib, `admin_catalog_service`ga o‘tadi. Product form `name_uz/ru`, descriptions, SKU/barcode, category, price/old price, stock/unit/min quantity, active/featured, sort order, tender lot URL’ni qo‘llaydi. Category form name/description/parent/image/sort/active’ni qo‘llaydi. Image endpointlari upload, primary belgilash, tartib o‘zgartirish va o‘chirishni beradi; `product_images` va public product media ishlashda davom etadi.

SKU unique, narx musbat, stock manfiy emas, `min_order_qty >= 1`; media format/size joriy validatsiya qoidasiga bo‘ysunadi. Product image API: `POST /api/v1/admin/products/{id}/images`, `PATCH /.../images/{image_id}` primary/sort uchun, `DELETE /.../images/{image_id}`. Category cover API: `PUT /api/v1/admin/categories/{id}/image` va `DELETE /api/v1/admin/categories/{id}/image`. Category parent o‘zini yoki descendant’ini ko‘rsata olmaydi; ierarxiya edit/delete bitta category-tree advisory lock ostida tekshiriladi, parallel parent edit ham cycle yarata olmaydi. Existing ierarxiya chuqurligi ikki daraja bilan cheklanmaydi. Category hard delete product yoki child mavjud bo‘lsa `409 CATEGORY_IN_USE`; product order history’ni snapshot orqali saqlaydi. Tender lot URL faqat HTTPS URL bo‘lishi mumkin. Mahsulot count denormalization service transaction’da yangilanadi.

Product/category edit request oldingi server `edit_version`ni yuboradi. Row lock’dan keyin version o‘zgargan bo‘lsa `409 ENTITY_CONFLICT`; UI draftni saqlab, yangilangan qiymatni ko‘rsatadi. Version katalog edit va stock o‘zgarganda oshadi, oddiy view counter’da oshmaydi. Phase 1 checkout/cancel stock adjustment ham version’ni oshiradi, shu sabab eski admin formasi yangi sotuvdan keyingi stock’ni bosib ketmaydi. Image primary/reorder amali product lock ostida bir vaqtda ko‘pi bilan bitta asosiy rasmni qoldiradi. Bot FSM ham shu service va version qoidalaridan foydalanadi.

### Foydalanuvchilar

`GET /api/v1/admin/users` qidiruv/pagination bilan user list; `GET /.../users/{id}` order count/first-touch source va block state; `PATCH /.../users/{id}/block` faol/to‘siq holatini boshqaradi. Umumiy user list/detail va block amali manager/superadmin uchun; operator faqat ishlashga ruxsatli order detail’dagi zarur customer name/phone/address’ni ko‘radi. Block customer auth’da keyingi request’ni rad etadi. User list’da telefon masklangan, to‘liq qiymat detail’da; audit va loglarda telefon/token yo‘q.

### Sozlamalar

`GET /api/v1/admin/settings` typed sozlamalar, server `settings_version` va readiness’ni; `PATCH /api/v1/admin/settings` validatsiyalangan delta va expected version’ni qabul qiladi. Settings mutation bitta store-state row lock ostida version’ni tekshiradi va oshiradi; parallel bot/web formadan stale saqlash `409 ENTITY_CONFLICT` oladi. Forma delivery fee, free threshold, minimum, `work_hours`, `card_number`, `card_holder`, support username/phone, `is_shop_open`, welcome uz/ru’ni qamraydi. Narxlar manfiy bo‘lmaydi; shop-open haqiqiy bool; phone/username/url o‘z formatida tekshiriladi. Gateway merchant secrets `.env`/deploy secret’da qoladi, web admin’da ko‘rsatilmaydi va API response/audit’da saqlanmaydi.

`null` yoki yo‘q qiymat admin readiness checklist’da “sozlanmagan” bo‘lib ko‘rinadi. Haqiqiy do‘kon qiymatlari dastur yozish/testini to‘xtatmaydi: katalog, savat, buyurtmalar tarixi va admin ishlaydi; faqat yangi quote/checkout phase1 bo‘yicha fail-closed qoladi. UI hech qanday demo narx, karta raqami yoki support username yozmaydi. Owner keyin haqiqiy delivery fee, minimum, free threshold va payment launch’ni belgilaydi. Click/Payme live payment bu bosqichda yoqilmaydi; secret qiymat kiritish va provider owner review’dan keyin alohida release qarori bo‘ladi, Paynet esa yashirin qoladi.

### Xodimlar, rol va sessiyalar

`GET/POST /api/v1/admin/team`, `PATCH/DELETE /api/v1/admin/team/{admin_id}`, `POST /api/v1/admin/team/{admin_id}/sessions/revoke` superadmin-only. Add Telegram ID, ism va role oladi; `is_active`/`notifications_enabled` alohida boshqariladi. O‘zini o‘chirish taqiqlanadi; UI so‘nggi faol superadminni demote/deactivate/delete qilishga yo‘l qo‘ymaydi, server ham rad etadi.

Last-superadmin invariant uchun staff add/promote/demote/activate/deactivate/delete amallarining barchasi transaction ichida bitta PostgreSQL `pg_advisory_xact_lock` kalitini oladi, keyin active superadmin count’ini qayta o‘qib write qiladi. Bir vaqtdagi ikki demotion’dan kamida bittasi `409 LAST_SUPERADMIN_REQUIRED` oladi. Role/deactivation/removal auth epoch’ni oshiradi va session’larni revoke qiladi.

### Statistika, traffic source va export

`GET /api/v1/admin/stats/overview?period=today|week|month` va `GET /api/v1/admin/stats/export.xlsx?period=...` superadmin/manager/operator uchun read-only. Botdagi stat formulasiga mos `orders_count`, `order_value`, `avg_check`, `new_users`, top products qaytariladi; `paid_amount` `payment_status=paid` va cancelled bo‘lmagan orderlardan hisoblanadi. `order_value` cancelled bo‘lmagan order totals’ini payment state’dan qat’i nazar yig‘adi; u kassaga tushgan pul deb nomlanmaydi. API’dagi eski `revenue` response maydoni buzilmaydi; bot/web UI va Excel uni aniq “bekor qilinmagan buyurtmalar summasi” deb belgilaydi.

`GET/POST /api/v1/admin/sources`, `GET/PATCH /.../sources/{id}` manager/superadmin-only. Campaign name/code linkini ko‘rsatadi, stats clicks/users/orders/order value hisoblaydi, active toggle qiladi. Birinchi-touch `users.traffic_source_id` o‘zgarmaydi. Ishlatilgan source fizik o‘chirilmaydi; inactive qilish yangi attribution’ni to‘xtatib tarixni saqlaydi.

### Broadcast

`POST /api/v1/admin/broadcasts/preview` target (`all`, `active`, `buyers`) bo‘yicha recipient soni va kontent tekshiruvini qaytaradi, hech kimga xabar yubormaydi. `POST /api/v1/admin/broadcasts` draft yaratadi. Faqat `POST /api/v1/admin/broadcasts/{id}/launch` aniq tasdiqdan keyin audience snapshot’ini oladi va yuborishni boshlaydi; `GET /{id}` progress/status, `POST /{id}/cancel` esa pending recipientlarni to‘xtatadi.

Launch body preview fingerprint/count va UUID idempotency key olib keladi. Fingerprint tartiblangan recipient ID’lari, target va aynan ko‘rsatilgan matn/rasm/button kontentini bog‘laydi. Audience o‘zgargan bo‘lsa `409 BROADCAST_AUDIENCE_CHANGED`, kontent o‘zgargan bo‘lsa `409 BROADCAST_PREVIEW_CHANGED`; yangi preview’dan keyin admin qayta tasdiqlaydi. `broadcast_recipients` jadvali `(broadcast_id,user_id)` unique, status `pending/sending/sent/failed/cancelled`, attempt, lease token/expiry, next retry, sent time va oxirgi sanitized xatoni saqlaydi. PostgreSQL `broadcast_status` enum’iga `cancelled` qiymati qo‘shiladi. Launch audience snapshot’i, broadcast status’i va delivery rows bitta transaction’da yoziladi. Restart’da `pending`/muddati o‘tgan `sending` qayta olinadi; oldin yuborilgani DB’da saqlangan bo‘lsa qayta yuborilmaydi.

Bot boshiga barcha worker, outbox va broadcast uchun umumiy Redis pacing gate ko‘pi bilan 20 msg/sec’ni va Telegram `RetryAfter`ni hurmat qiladi. Vaqtinchalik xatolar backoff bilan qaytariladi; `Forbidden` user’ni blocked qiladi; permanent failure audit/count’da qoladi. Dispatch oldidan mijoz block holati, job cancel holati va launch qilgan actor’ning joriy huquqi qayta tekshiriladi. Cancel yoki actor huquqi bekor qilinishi hali yuborilmagan ishlarni to‘xtatadi; allaqachon network’da bo‘lgan xabar qaytarib olinmaydi. “Launch”dan tashqari draft, preview, sahifa ko‘rish yoki browser reload xabar yubormaydi. Telegram yuborishi va DB checkpoint bitta atomic amal bo‘lmagani uchun yuborishdan keyingi ack crash’i ayrim recipient’ga takror yuborishi mumkin; durable checkpoint yetkazishni at-least-once qiladi, exactly-once emas.

## Transactional notification outbox

Order create/status/cancel/payment acceptance va muhim team/settings mutation’lari `notification_outbox` eventini o‘sha business transaction’da yaratadi. Minimal row: event ID/type, aggregate ID, unique dedupe key, created/available time, attempt count, lease token/expiry, sent time va sanitized last error. Bitta outbox row bitta recipient/delivery amalidir; dedupe key event ID/version, recipient va amal turini o‘z ichiga oladi. Adminlarga fan-out recipient boshiga alohida row yaratadi, shunda bitta xatoda avval yetkazilgan barcha admin xabarlari qayta ketmaydi. Event’da raw phone, receipt bytes, token, card number yoki gateway raw payload bo‘lmaydi; worker order/admin/user row’larini ID bilan yuklaydi. Admin yuboradigan xabar matni protected `admin_order_messages` row’ida saqlanadi, outbox faqat uning ID’siga murojaat qiladi.

FastAPI lifespan mavjud `app.state.bot` bilan bitta asynchronous dispatcher task’ni boshlaydi. Worker qisqa transaction’da `FOR UPDATE SKIP LOCKED` orqali batch claim qiladi va lease qo‘yadi; Telegram send network call’i DB lock’dan tashqarida bo‘ladi; keyin sent/retry state yangi transaction’da faqat aynan shu lease token egasi tomonidan yoziladi. Crash bo‘lsa lease tugagach boshqa worker qayta oladi. Bir nechta API instance ham shu qoidani ishlatadi. Shutdown’da worker to‘xtatilib lease’lar expiry orqali tiklanadi. Phase 1’dagi shu eventlarga tegishli post-commit direct send outbox bilan almashtiriladi; ikkalasi parallel yuborib duplicate yaratmaydi.

Bu at-least-once delivery. Telegram `sendMessage` idempotency key bermaydi, shuning uchun send muvaffaqiyatli bo‘lib DB ack’dan oldin process yiqilsa duplicate DM ehtimoli bor; exactly-once deb va’da berilmaydi. Order-card update current DB state’dan qayta chiziladi; delivery event dedupe key’i source status-history/payment-review version’dan olinadi. Broadcast recipient checkpoints alohida jadvalda bo‘ladi, umumiy notification outbox broadcast progress o‘rnini bosmaydi.

## Audit va mutation qoidalari

`admin_audit_events` har admin mutation’i bilan bir transaction’da yoziladi: actor admin ID va serverdan olingan actor_name_snapshot, action, entity/entity ID, request ID, time, redacted before/after diff. Snapshot staff hard-delete’dan keyin ham kim amal bajarganini saqlaydi. Order status uchun mavjud `order_status_history` canonical qoladi; payment acceptance reviewer/version ham ko‘rinadi. Product/price/stock/category/settings/user block/team/source/broadcast preview-launch-cancel/session revoke amallari audit qilinadi.

Card number faqat masklangan oxirgi 4 raqam; provider secret, login code, session/CSRF token, receipt bytes va user telefonining to‘liq qiymati auditga tushmaydi. Audit yozuvlari o‘zgartirilmaydi va avtomatik o‘chirilmaydi. `GET /api/v1/admin/audit` filter/pagination beradi: superadmin barcha; manager operatsion/catalog/broadcast; operator faqat `actor_admin_id` o‘ziga teng bo‘lgan order/payment/admin-order-message event’larni ko‘radi; o‘zining eski team/session/customer event’lari ham yopiq qoladi. Order detail’dagi mavjud `order_status_history` operatorning order-view ruxsati bo‘yicha ko‘rinadi.

## DB va xato kontrakti

Alembic migration additive bo‘ladi va Phase 1’ning xarid reliability migration head’idan davom etadi: reja bo‘yicha `1e6b8d02a9c4` (`9c1f4a7be2d0`dan keyin), hech qachon original `origin/main` head’dan alohida branch ochmaydi. `admins.auth_epoch`, product/category `edit_version`, settings revision uchun store-state, `admin_sessions`, `notification_outbox`, `broadcast_recipients`, `admin_order_messages` va `admin_audit_events` qo‘shiladi; `broadcast_status` enum’iga `cancelled` qo‘shiladi. `broadcast_recipients(broadcast_id,user_id)` va `notification_outbox.dedupe_key` unique; image primary/order uchun mavjud `product_images.is_main/sort_order` ishlatiladi. Phase 1’dagi checkout, private receipt va manual payment review ustunlari saqlanadi; mavjud business ma’lumotlari, product media va private receipt storage saqlanadi. `admin_role` enum o‘zgartirilmaydi; admin session FK admin delete’da cascade/revoke qilinadi, audit actor FK esa history’ni o‘chirmaydi.

Admin API xatolari mavjud `{error:{code,message,details}}` formatida: `401 ADMIN_SESSION_REQUIRED`, `403 ADMIN_ROLE_REQUIRED`, `403 CSRF_FAILED`, `409 LAST_SUPERADMIN_REQUIRED`, `409 BROADCAST_AUDIENCE_CHANGED`, `409 BROADCAST_ALREADY_LAUNCHED`, `409 ENTITY_CONFLICT`, `422 VALIDATION_ERROR`, `404 NOT_FOUND`. Wrong/expired/used admin code bir xil `401 INVALID_OR_EXPIRED_CODE` qaytaradi. Client error’da PII yoki stack trace bo‘lmaydi.

## Qabul qilish mezonlari

1. Desktop va 360px mobile’da admin shell, session-expired holati va role-based nav ishlaydi; `/admin` customer Telegram initData talab qilmaydi.
2. Private-code exchange bitta parallel winner beradi; cookie Secure/HttpOnly/SameSite, CSRF/Origin checks va idle/absolute expiry tekshiriladi; logout, logout-all, admin deactivation, role change va epoch increment sessiyani bekor qiladi. Eski Bearer admin JWT `/admin/*`ga kira olmaydi; Phase 1 buyer JWT cart/checkout’ga kira oladi.
3. Superadmin/manager/operator matrix har endpoint’da server side test qilinadi. FSM shaklini manager ochib, role o‘zgargandan keyin saqlashga urinsa mutation rad etiladi.
4. Katalog CRUD, multipart image upload CSRF guard’i, primary/reorder/delete, tender URL, count va category-in-use/cycle guard bot/web’dan bir xil natija beradi. Eski admin stock formasi bilan parallel checkout hamda ikki stale product/settings formasi conflict beradi va yangi qiymatni bosib ketmaydi.
5. Order detail private receipt, phase1 payment acceptance va status history’ni ko‘rsatadi; foreign/inactive admin receipt ololmaydi.
6. Settings type/range errors, null readiness, existing order instruction snapshot va public readiness tekshiriladi. Production narx/karta/support default’i avtomatik yozilmaydi.
7. Operator stats oladi; cancelled/count, order value, paid amount va avg check ta’riflari API/XLSX/bot label’da bir xil. Source attribution first-touch o‘zgarmaydi; used source deactivate qilinadi, hard delete qilinmaydi.
8. Last-superadmin ikki parallel mutation testidan hech qachon nol active superadmin chiqmaydi; audit row business write bilan birga commit yoki rollback bo‘ladi.
9. Broadcast preview/draft/test request hech kimga xabar yubormaydi; launch explicit, idempotent, kontent/audience snapshot’li va recipient checkpoint bilan restart’dan davom etadi. Fake bot’da umumiy pacing, RetryAfter, Forbidden/block, duplicate launch, kontent o‘zgarishi, revoked actor, cancel va crash recovery test qilinadi.
10. Outbox event business rollback’da yo‘qoladi; process restart’dan keyin pending row yetkaziladi; ikki worker bir row’ni bir vaqtda claim qilmaydi va eski lease token yangi claim’ni ack qilmaydi. Per-recipient fan-out va direct-send o‘chirilgani tekshiriladi; send/ack crash oynasi at-least-once limitation sifatida qayd etiladi.

Backend testlari fake bot va disposable PostgreSQL/Redis’da; `notification_outbox`/broadcast checkpoint concurrent testi haqiqiy ikki DB session bilan bajariladi. Hech qachon production admin, customer, token yoki real broadcast ishlatilmaydi. Manual browser checks `/admin` desktop/mobile va uz/ru, session revoke va bot/web shared updates’ni qamraydi.

## Release va keyingi bosqich

Owner hali haqiqiy delivery fee, minimum, free threshold va online payment launch’ni belgilamagan. Bu qiymatlarni kutish software ishini to‘xtatmaydi: admin setup checklist ularni missing deb ko‘rsatadi, uydirma qiymat/card/support kiritilmaydi va checkout phase1 bo‘yicha fail-closed qoladi. Provider credentials deploy secret’da qoladi; testlarda synthetic.

Phase2 Kans Shop private receipt volume’ni saqlaydi; media migration/public deny/rollback qoidalari phase1 dizayni bilan bir xil. Kans API/React/static proxy va Netcup’dagi shu store konfiguratsiyasidan tashqari shared PostgreSQL, Redis, boshqa Netcup stack yoki domain o‘zgarmaydi. Owner review, backup, migration compatibility va SHA asosidagi CI/deploy dalili release’dan oldin talab qilinadi.

Phase3 faqat storefront UX: mobil/desktop vitrinasini yangilash, qidiruv/pagination, til va customer account/order presentation. Bu admin role/auth, catalog data yoki purchase policy’ni qayta belgilamaydi.
