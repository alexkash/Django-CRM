# Ukrainian Billing Implementation Plan

> Исторический документ проектирования/планирования. После его подготовки пользователь отдельно поручил реализацию и создание четырёх последовательных PR с ревью Codex. Фактический результат и проверки описаны в отчёте реализации.

> **Статус исполнения, 2026-10-15:** пользователь отдельно поручил создать worktree и реализовать план. T1–T7 выполнены inline; результаты, исправления ревью и baseline-ограничения — в [отчёте реализации](2026-10-15-ukrainian-billing-implementation.md). Текст исходных checklists ниже сохранён как история плана.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Execution method is not selected; this request authorizes planning and plan audit only. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В одной CRM вручную выпускать украинские счета и частичные акты от нескольких ФОП/ТОВ с отдельным ПДВ и печатными сканами подписи/печати.

**Architecture:** Расширяем Invoice opt-in связью с LegalEntity; существующие обычные счета сохраняют поведение. Новые справочники и акты размещаем в пакете `invoices.billing` внутри существующего Django app, выпуск сохраняет snapshot и два неизменяемых PDF; частичные акты расходуют остатки позиций под блокировкой Invoice.

**Tech Stack:** Python >=3.12, Django/DRF, PostgreSQL, существующий WeasyPrint, Pillow (в среде проекта для ImageField; при прямом использовании явно закрепить зависимость в pyproject/uv.lock), Svelte 5/SvelteKit, Vitest, pytest. Lock-файлы сохраняют текущие версии, обновление стека не входит.

**Spec:** [Требования, решения и дерево](../specs/2026-10-15-ukrainian-billing-design.md). Пользователь прямо запросил дерево → план → аудит; запуск реализации этим не разрешён.

## Global Constraints

- Одна Org; несколько LegalEntity, ручной выбор исполнителя. Новых tenant-контейнеров нет.
- «Ввод цены без ПДВ, отдельно сумма без ПДВ, сумма ПДВ, затем итог с ПДВ.»
- «Создаём документы по одному вручную; копирование в новый черновик.»
- «Один счёт может закрываться несколькими частичными актами. Оплата и закрытие услуг независимы.»
- «Реквизиты выпущенного документа, его суммы и используемые сканы не меняются при изменении справочников.»
- Сканы необязательны; КЕП, внешняя отправка, расписания, нотификации, входящие документы, полноценный договорный модуль и новый mobile UI вне первой версии.
- Только новые счета с issuer используют украинский режим (UAH, одна ставка, без скидок/shipping); старые счета/estimates/recurring не меняют расчёт и не конвертируются автоматически.
- Все новые таблицы — BaseOrgModel с org-индексами, регистрацией ORG_SCOPED_TABLES и реальной FORCE RLS миграцией; каждый API отдельно фильтрует Org и права на родительский счёт.
- Тестовые стороны и сканы синтетические. Downloads, реальные реквизиты и подписи не коммитить.
- Существующий worktree/ветка `alexkash/install` сохраняются. До реализации повторно сверить HEAD и рабочие изменения; не применять reset/stash, не затирать параллельную работу. Коммиты — только при отдельном разрешении.

## Review Focus

1. Замена компании/банка/скана/клиента после выпуска не меняет ни один байт архивного PDF; старые generic документы сохраняют динамический PDF. T3/T6.
2. Два одновременных выпуска актов на последний остаток и повтор issue не должны расходовать объём/номер дважды. T4/T7.
3. Годовая позиция quantity=1, двенадцать частей, копейки и бесплатная строка не дают деления на ноль или расхождения итогов. T2/T4.
4. Скрытый в своей Org счёт не раскрывается актами, PDF, сканами, списками или итогами; bank/payer/source_line другой компании/Org не принимаются. T1/T4/T5/T7.
5. Send, mark-paid, standalone line endpoints, admin, workers, estimate conversion и duplicate не обходят выпуск/заморозку UA, не меняют generic поведение. T3/T6.

## 1. Источник, текущие факты и рабочее дерево

Исходные решения и состав образцов полностью зафиксированы в spec §§1–2. Перед изменениями executor читает spec и этот план целиком.

Применимые правила: корневой `AGENTS.md` (появился во время параллельной работы, прочитан до завершения плана), пользовательские рабочие предпочтения из чата, CONTRIBUTING.md и routed docs/contributing. Обязательное итоговое покрытие ≥50% по `.coveragerc`; focused и PostgreSQL прогоны могут быть без coverage.

Проверено по дереву на HEAD `f3f9053a` (2026-10-15):

- `backend/common/models.py:Org` — один профиль компании, не список продавцов; `accounts/models.py:Account` не имеет отдельного набора юридических/банковских полей.
- `backend/invoices/models.py:Invoice`, `InvoiceLineItem`, `LineAmounts`, `_next_number`, `Invoice.recalculate_totals`: отдельная header tax, line tax сейчас не добавляется в общую сумму; уникальность номера `(org, invoice_number)`; default генерация номера при save. Изменять это глобально нельзя.
- `invoices/serializer.py:refuse_issued_amount_changes` блокирует строки/финансы, но оставляет даты/notes/реквизиты изменяемыми. Обновление nested line_items удаляет и создаёт строки заново.
- `invoices/permissions.py:visible_invoices_qs/get_invoice_or_error` уже дают одинаковый 404 скрытой/чужой записи. `accounts/access.py:visible_accounts_qs` — контракт видимости клиента.
- `InvoiceSendView`, `InvoiceMarkPaidView`, `InvoiceCancelView`, `InvoiceDuplicateView`, `EstimateConvertView`, `InvoiceFromOpportunityView`, `InvoiceFromTimeEntriesView` и `invoices/tasks.py:_generate_one` — существующие потребители Invoice. Учитывать каждый, не рефакторить весь файл api_views.py.
- `invoices/pdf.py:generate_invoice_pdf` использует текущий Org и текущий template; `PublicInvoicePDFView` и `send_invoice_to_client` вызывают тот же renderer. `SafePdfURLFetcher` ограничивает файловый/сетевой доступ; его ограничения не расширять ради сканов.
- Frontend: `lib/server/v2/invoices.js` нормализует money в JS Number; для новых финансовых форм сохранять исходные decimal-строки при отправке, итог на сервере. Есть `/invoices/[id]/pdf/+server.js`; `/invoices/[id]/edit/` отсутствует, нужен новый маршрут.
- `frontend/vitest.config.js` не компилирует Svelte; unit tests — plain JS сервисы/actions, UI проверять настоящим браузером без перестройки всего harness.
- CI `.github/workflows/tests.yml` **уже** содержит SQLite, PostgreSQL и policy-bound `postgres_only` прогоны; `crm/test_settings_postgres.py` существует. Некоторые docs/contributing/testing.md сведения об отсутствии этого job устарели; источником команд являются текущие CI/settings. Не добавлять второй PG harness.
- Есть существующие планы в `docs/superpowers/plans/`, поэтому используем эту директорию.

При обследовании уже были чужие изменения frontend: server/v2 (deals, products, search), Sidebar/StageMeter/enums, страницы accounts/contacts/invoices/leads/pipeline/settings/tasks, новые legacy-модули и routes. Состав может измениться; сохранять их. Нынешний план редактирует только три новых Markdown-файла design/plan/audit, без коммита.

## 2. Контракты реализации

### 2.1 Данные и суммы

Полный набор полей — spec §4.2; exact model names: LegalEntity, LegalEntityBankAccount, DocumentSequence, ServiceAct, ServiceActLine. Все пять — новые таблицы в app invoices; импортировать их в `invoices/models.py` для обнаружения Django, не допуская циклов (`ForeignKey` строковыми ссылками). `InvoiceLineItem.unit` и `Product.unit` — копирование единицы, default `послуга` только для новых UA-строк без указанной единицы, старые строки не переписывать.

Публичные чистые функции:

- `calculate_ua_totals(lines: Sequence[LineInput], vat_status: str, vat_rate: Decimal) -> UATotals`: возвращает сохранённые line net/VAT/gross и document subtotal/tax/total, только Decimal + ROUND_HALF_UP; контракт чисел spec §4.3. Суммы БД Decimal(12,2); явная ошибка переполнения до записи, quantity/price должны помещаться в существующие поля InvoiceLineItem.
- `allocate_act_line(source: SourceLineBudget, requested_quantity: Decimal, issued: IssuedAllocation) -> ActAllocation`: количество не более 8 знаков (лишние знаки отклоняются, не округляются молча). Dataclasses LineInput/UATotals/SourceLineBudget/IssuedAllocation/ActAllocation определяются в money.py и экспортируются оттуда, с Decimal-полями названных budget/totals. Остатки `Rq=source.quantity-issued.quantity`, `Rn=source.net-issued.net`, `Rv=source.vat-issued.vat`; при `0<q<Rq`: net=round(Rn*q/Rq), vat=round(Rv*q/Rq), ROUND_HALF_UP до копейки; при q=Rq — ровно Rn/Rv. Результат всегда 0..остаток, в том числе при сумме0.07 и 12 актах, отменах/повторном выпуске; не применять независимое округление исходной суммы для каждого акта. Не использовать float. При нулевом net не делить на него. Запрошенный q>0 и ≤остатка, unit и цена не изменяются.
- `amount_in_words_uk(amount: Decimal) -> str`: UAH 0..9_999_999_999.99, украинские окончания (1/2–4/5+, 11–14, тысячи женского рода), копейки всегда две цифры; не вводить отдельный генератор документов или AI API.

При q_source=1 и 12 равных периодах первые 11 вводят `0.08333333`, последняя операция «весь остаток» использует `0.08333337`; UI показывает точный остаток и не округляет его до двух знаков. Для удобства годовую поддержку можно завести 12 `місяць`. Точные даты начала/конца периода обязательны при выпуске UA (не при сохранении неполного draft), start <= end, порядок сверяется сервером; период акта внутри периода услуг счёта, а issue_date может быть позднее оказания услуг; совпадение периодов само по себе не запрещает разные части работ.

### 2.2 Выпуск и immutable snapshot

Во всех service signatures `actor` — authenticated DRF Request с серверными user/profile; сервисы используют именно этот org context и existing access helpers. Money-функции не зависят от Request/ORM.

- `create_ua_invoice(*, actor, org, validated_data) -> Invoice`; mode определяется непустым issuer, org/creator серверные. Нельзя снять issuer и превратить UA в generic даже в черновике. До выпуска можно выбрать другое активное своё юрлицо/банк с повторной валидацией; после — нельзя.
- `issue_invoice(*, actor, invoice_id) -> Invoice`: atomic, get_invoice_or_error, lock Invoice, validate prerequisites, lock sequence, prepare snapshot, render clean/stamped bytes, сохранить суммы/номер/snapshot/pdf/hash/issued_at и wire-status Sent. Ничего не отправляет. Повтор issue возвращает тот же результат; missing renderer →503, ошибка рендера →неуспех без partial state.
- `create_act(*, actor, invoice_id, data) -> ServiceAct`; `update_act(*, actor, act_id, data) -> ServiceAct`; `issue_act(*, actor, act_id) -> ServiceAct`; `cancel_act(*, actor, act_id, reason) -> ServiceAct`. Все mutations берут Invoice → Act → sequence; auth до раскрытия состояния. Issue заново рассчитывает остаток по Issued актам, а не доверяет черновику. Повторный issue/cancel идемпотентен.
- `get_closure_summary(invoice) -> {closed_net, closed_vat, closed_total, remaining_net, remaining_vat, remaining_total, lines}`: Issued only, без join-multiplication; payment totals независимы. Cancelled acts не расходуют бюджет. UI отдельно показывает unpaid и remaining_to_close.
- Snapshot version=1: document kind/number/date/place/period, contract/order, seller/bank/customer/payer/signer реквизиты, строки с единицами/количествами/net/VAT/gross, vat_status/rate, totals, слова, texts, template_version, hashes сканов. Текст в snapshot и все printable invoice-поля после issue read-only; comments/attachments/payment могут жить отдельно.
- UA-модель не пересчитывает сохранённые выпущенные суммы на save системными задачами. UA InvoiceLineItem и ServiceActLine после issue не меняются; замена nested lines запрещена. Issued и Cancelled документы не удаляются. UA-записи и сканы в Django admin доступны только для чтения (включая inlines/bulk delete), изменения — только через сервисы.
- UA создаётся с `reminder_enabled=False`, `public_link_enabled=False`; generic serializers не позволяют включить эти опции у UA. Публичные UA routes возвращают 404. Для email Send UA сначала требует issue и использует архив; payment до issue отклоняется. Отмена Invoice с Issued актами отклоняется. `Payment.update_invoice_payment` для UA выводит unpaid status из issued_at (Sent либо Overdue по due_date), не из отсутствующего sent_at; удаление последней оплаты не возвращает выпущенный UA в Draft. Для generic ветка без изменений.

### 2.3 Нумерация и PDF

`next_document_number(*, org, entity, kind) -> str` вызывается только внутри transaction после блокировки документа; строки sequence создаются при создании LegalEntity. Prefix в компании изменяем до первого выпуска соответствующего kind. Уникальность Invoice: условный Unique `(org, issuer, invoice_number)` WHERE issuer IS NOT NULL и сохранённый Unique `(org, invoice_number)` WHERE issuer IS NULL; убрать старое unconditional ограничение только после добавления новых совместимых. Для Act — Unique `(org, issuer, number)` на Issued/Cancelled, issuer — собственный immutable FK на компанию из invoice для DB constraint; Draft технический номер/NULL. Изменение invoice.issuer не затрагивает исторические номера. Старый Invoice.generate_invoice_number/_next_number при работе с Invoice обязан ограничивать queryset issuer IS NULL; для Estimate и других моделей scope не меняется. Иначе UA prefix INV-<today>-X ломает Cast старого генератора, а числовой prefix меняет его sequence.

`render_ua_pdf(snapshot: dict, *, signature: bytes | None, stamp: bytes | None) -> bytes`: только встроенные html/css и bound bytes, без пользовательского HTML/CSS. Для PDF использовать существующий WeasyPrint, отдельный закрытый fetcher для exact `billing-asset://signature`/`billing-asset://stamp`, запрет остальных URL. Кириллический шрифт из лицензированного файла пакета (DejaVu Sans + лицензия), относительный file URL не разрешать в общем fetcher: bytes шрифта подключить через такой же bound resource. Без зависимости от Downloads, macOS fonts или внешней сети. Указанные private asset URI создаёт только renderer.

`normalize_scan(upload) -> {png: bytes, sha256: str}`: PNG/JPEG, ≤2 MiB исходный и нормализованный, ≤16 MP, фактическая декодировка/повторное кодирование Pillow, обработка decompression bombs; SVG/HTML/ложный mime/анимация отклоняются. Ошибки не удаляют прежний скан. Хранение spec §4.4: BinaryField, без MEDIA URL и отдельного filestore; backing DB backup включает документы. Сериализаторы не отдают bytes, raw paths или base64 в list/detail. В normal manager/queryset Invoice, ServiceAct, LegalEntity по умолчанию defer binary columns; для select_related использовать явный defer связанных binary полей. Аудировать также CSV export, account nested invoice lists, workers и prefetch: binary не должны попадать в SQL projection обычных запросов и не должны лениво читаться сериализатором. PDF/scans/issue запрашивают только нужные bytes явно через отдельный queryset/values, без скрытого manager fallback. Query-capture regression проверяет отсутствие колонок, включая ordinary list/detail/CSV и связанные записи; это нужно помимо JSON assertions.

### 2.4 HTTP и frontend

Регистрировать billing include из существующего `invoices/api_urls.py`:

- `/api/invoices/billing/legal-entities/`, `/<id>/`: GET members, POST/PUT/PATCH admin, archive через PATCH active=false. No hard DELETE.
- `/api/invoices/billing/legal-entities/<id>/bank-accounts/`, `.../<bank_id>/`: scoped CRUD без удаления использованных; member GET, admin writes.
- `/api/invoices/billing/legal-entities/<id>/scans/<signature|stamp>/`: admin-only GET/PUT/DELETE; multipart upload, deletion только текущего исходника, архивы остаются.
- `/api/invoices/<id>/issue/`: POST, существующее право изменения счёта, idempotent 200; existing POST/PUT invoices принимают новые поля только opt-in. Detail/list добавляют issuer, period и closed/remaining без изменения существующих ключей.
- `/api/invoices/billing/acts/`: GET visibility-scoped filters invoice/account/issuer/status/period, POST с invoice_id + lines[{source_line_id, quantity}] + issue_date + period; detail GET/PUT, POST `/<id>/issue/`, POST `/<id>/cancel/`, GET `/<id>/pdf/?variant=clean|stamped`. Draft удаляется DELETE, Issued/Cancelled —400.
- `/api/invoices/<id>/pdf/?variant=clean|stamped`: default clean, draft watermark preview, issued archived bytes, 400 invalid variant. GET без побочных действий. Акты аналогично. Для generic запроса без variant прежнее поведение; параметр variants не меняет generic renderer.

404 скрытых/чужих объектов одинаковый, 403 только на известное действие администрирования своего справочника, 400 validation/недопустимый lifecycle, 409 exhaustion/stale draft при попытке выпускать уже недоступный остаток. Не отдавать остаток чужого invoice в ошибке.

Новые UI-пути — дерево spec §5. `invoices/[id]/edit/` новый; сканы идут через authenticated SvelteKit proxy без JWT в браузерном URL. Scan administration скрыта от members, backend всё равно проверяет admin. PDF proxy allowlist variant, private/no-store, auth + safe filename. Денежные поля отправлять строками; нельзя полагаться на JS Number previews для сохранения итогов. Act q хранится/передаётся точной строкой.

## 3. Задачи и зависимости

### Task 1: Справочники, схема и защита новых данных

**Depends:** нет. **Результат:** схема и API компаний/банков/реквизитов клиента/сканов, с реальной изоляцией.

**Files — create:** `backend/invoices/billing/{__init__,models,serializers,views,urls,access,assets}.py`; `backend/invoices/tests/test_ua_legal_entities.py`, `test_ua_assets.py`, `test_ua_migrations.py`; `backend/invoices/migrations/0016_ua_billing_schema.py`, `0017_ua_billing_rls.py`; `backend/accounts/migrations/0012_account_billing_details.py`.
**Modify:** `backend/invoices/models.py`, `api_urls.py`, `admin.py`; `backend/accounts/models.py`, `serializer.py`; `backend/common/rls/__init__.py`; `backend/pyproject.toml`, `uv.lock` только если Pillow не объявлен напрямую. Номера миграций перепроверить перед исполнением, при новых параллельных миграциях выбрать следующие, не переписывать применённые.

**Interfaces:** модели/поля spec §4.2 + Invoice поля §2.3 этого плана; exports `get_act_or_error(request, pk, *, for_update=False)` и `visible_acts_qs(profile)` через visible parent invoices; `normalize_scan` §2.3. Не создавать временные stub API, которые принимают выпуск до готовности T3/T4.

- [ ] RED: allowed admin create/read; member write403; hidden/foreign404; bank чужой компании/Org400/404; scan real PNG/JPEG/поддельный mime/SVG/oversize/bomb; отсутствие bytes в обычном JSON. Данные старого Account остаются валидными.
- [ ] Run RED: `cd backend && uv run pytest --no-cov invoices/tests/test_ua_legal_entities.py invoices/tests/test_ua_assets.py -q` — ожидаются только ошибки отсутствующей функциональности.
- [ ] Реализовать schema, RLS миграцию после CreateModel, constraints (q>0, nonnegative amounts, unique sequences, `(act,source_line)`), орг-индексы и serializers read-only server fields. При schema вводить UA только nullable/additive; не backfill issuer/юридические данные по догадке. Scan fields и PDF fields не включать в общий ModelSerializer `__all__`.
- [ ] GREEN: тот же pytest; `DJANGO_SETTINGS_MODULE=crm.test_settings uv run python manage.py makemigrations --check --dry-run`; `DJANGO_SETTINGS_MODULE=crm.test_settings uv run python manage.py migrate --plan`. MigrationExecutor test миграции с предыдущего state на синтетических generic документах и назад, без реальных БД.

### Task 2: UA-черновики, расчёт и нумерация

**Depends:** T1. **Результат:** создание/редактирование корректного UA черновика через существующий invoices API, без изменения generic расчёта.

**Create:** `backend/invoices/billing/{money,numbering,services,formatting}.py`; `backend/invoices/tests/test_ua_money.py`, `test_ua_invoice_drafts.py`, `test_ua_numbering.py`, `test_ua_query_projection.py` (SQL проверка deferred blobs).
**Modify:** `backend/invoices/{models,serializer,api_views}.py`; существующие `invoices/tests/test_document_numbers.py` только для сохранения generic контракта; Product serializer поля unit.
**Interfaces:** функции §§2.1–2.3; `InvoiceCreateSerializer` принимает issuer_id/bank_account_id/payer_id/contract/date/period/place; `InvoiceSerializer` возвращает новые поля additive. Подставляет реквизиты из видимого Account, допускает структурированные поправки в draft snapshot; на issue повторно проверяет обязательные данные.

- [ ] RED: net=10000 + VAT20%=2000 →12000; NON_PAYER →10000/0/10000 и явный статус; несколько строк с округлением на строке; 0.01/большая сумма/overflow/нулевая цена/отрицательное q/цена; rate 0 не превращает PAYER в NON_PAYER. Скидки/shipping для UA отклоняются явно, generic остаются рабочими.
- [ ] RED: draft technical number не расходует sequence; remove issuer запрещён; банк/плательщик проверены; unit и price копируются и не меняются при обновлении каталога; payer Account невидим/чужой отклоняется. Пересекающиеся UA префиксы INV-<today>-X и INV-<today>-123 не влияют на generic Invoice allocation и не ломают Cast на PostgreSQL. Money words: 0,1,2,5,11,21,1001,1011,дробные копейки, максимальная сумма.
- [ ] Run RED: `cd backend && uv run pytest --no-cov invoices/tests/test_ua_money.py invoices/tests/test_ua_invoice_drafts.py invoices/tests/test_ua_numbering.py -q`.
- [ ] Реализовать create/update UA и opt-in ветку пересчёта. Применить conditional constraints номеров и исключение issuer rows из старого Invoice allocator. Реализовать default defer и explicit binary loaders; проверить ordinary list/detail/CSV/related queries на отсутствие archive/scan колонок. Изменение prefix после первого соответствующего выпуска отвергается; schema migration из T1 при необходимости дополняется следующей миграцией, не переписывается после применения.
- [ ] GREEN: те же файлы + `uv run pytest --no-cov invoices/tests/test_document_numbers.py invoices/tests/test_line_discount_totals.py invoices/tests/test_tax_and_shipping_bounds.py -q`.

### Task 3: Выпуск счёта и две неизменяемые печатные формы

**Depends:** T2. **Результат:** выпустить и распечатать счёт без отправки; PDF не изменится после правок справочников.

**Create:** `backend/invoices/billing/pdf.py`; `backend/invoices/templates/invoices/pdf/ua/{invoice.html,act.html,billing.css,fonts/DejaVuSans.ttf,fonts/LICENSE}` (act template используется T4); `backend/invoices/tests/test_ua_issue.py`, `test_ua_pdf.py`, `test_ua_snapshot.py`.
**Modify:** `billing/services.py`, `billing/views.py`, `invoices/api_urls.py`, `invoices/pdf.py`, `api_views.py`, `serializer.py`, `admin.py`.
**Interfaces:** `issue_invoice` и `render_ua_pdf` §§2.2–2.3; новая `UAInvoiceIssueView`; `generate_invoice_pdf` dispatch UA на watermark preview/архив, generic прежний путь. Опция clean/stamped не попадает в custom generic HTML.

- [ ] RED: issue не вызывает email/Celery; archived clean/stamped разные при синтетических сканах; replace/delete scans, bank/client edits, template edits и payments не меняют hashes; missing scan не блокирует. Draft GET PDF оставляет status/sequence без изменений.
- [ ] RED: failure между render clean и stamped откатывает snapshot/номер/issued_at; повтор issue даёт тот же номер и bytes; после issue нельзя поменять реквизиты, payer, dates/period, texts/unit/lines через PUT, standalone lines или admin.
- [ ] Run RED: `cd backend && uv run pytest --no-cov invoices/tests/test_ua_issue.py invoices/tests/test_ua_pdf.py invoices/tests/test_ua_snapshot.py -q`.
- [ ] Реализовать atomic issue и bounds PNG/PDF, экранирование, закрытый resource fetcher, licensed packaged font. Для binary PDF не выдавать URL хранения; ответы private/no-store; snapshot/pdf/hashes server-only. Preview не должен раскрывать raw scans через другие endpoints.
- [ ] GREEN: те же tests + `test_custom_template_escaping.py`, `test_template_editor.py`, `test_admin_issued_lock.py`, `test_issued_documents_locked.py`, `test_issued_totals_frozen.py` в `invoices/tests/`. Render реальным WeasyPrint, не mock всей цепочки.

### Task 4: Частичные акты и остатки по позициям

**Depends:** T3. **Результат:** ручной частичный акт с собственной нумерацией/PDF; безопасное повторное закрытие после отмены.

**Create:** `backend/invoices/tests/test_ua_acts.py`, `test_ua_act_allocation.py`, `test_ua_act_access.py`, `test_ua_act_races.py`.
**Modify:** `billing/{services,money,serializers,views,urls,access}.py`, `invoices/serializer.py`, `api_views.py` (closure summary/защита отмены), `billing/pdf.py`, act.html.
**Interfaces:** act functions и closure summary §2.2. Вся информация issuer/customer/payer/contract для акта берётся из snapshot выпущенного счёта, не из изменившегося Account/юрлица. Для сканов при выпуске акта использовать текущие сканы исходного юрлица, зафиксировав в новом архиве и hashes; если source entity архивирована, исходный счёт остаётся обслуживаемым и акт разрешён с его зафиксированными реквизитами.

- [ ] RED: yearly q=12×1000, 4 акта q3×3000 или12 актов q1×1000; yearly q1 с 8 десятичными разрядами; финальный остаток1коп; free line; net0.07/VAT0.01 и12 месячных частей с отменой/повторным выпуском; несколько строк с разными остатками; paid invoice всё ещё требует акт, unpaid issued invoice может иметь акт.
- [ ] RED: act draft не резервирует, issue пересчитывает, две конкурирующие заявки на последний остаток дают ровно один успех и один409; две разных строки исходного счёта не конфликтуют ложной unique; отмена освобождает остаток, повторная отмена не освобождает дважды. Issued акт не редактируется/удаляется, invoice cancel с действующим актом запрещён.
- [ ] RED: foreign/hidden invoice, act/source_line/payer/bank, период акта вне периода счёта, list/search/summary/PDF404 или пустой список без утечки. Принудительный payload org/issuer/totals/number не принимается как источник истины.
- [ ] Run RED: `cd backend && uv run pytest --no-cov invoices/tests/test_ua_acts.py invoices/tests/test_ua_act_allocation.py invoices/tests/test_ua_act_access.py -q`.
- [ ] Реализовать draft/edit/issue/cancel/delete-draft и API, aggregate only Issued, lock order и безопасную выдачу архивов. Не создавать Payment при выпуске акта. Schema serializer поля Act.issuer объявить read-only и выводить из Invoice.
- [ ] GREEN: тот же pytest. PostgreSQL race тесты из test_ua_act_races.py исполняются T7 как `postgres_only`, SQLite skip не считается доказательством гонки.

### Task 5: Настройки компаний и рабочий UI документов

**Depends:** T4. **Результат:** пользователь проходит весь ручной сценарий в существующем веб-интерфейсе.

**Create server:** `frontend/src/lib/server/v2/legal-entities.js`, `service-acts.js` и одноимённые `.test.js`; новые pure JS billing form helpers/tests при необходимости exact name `billing-forms.js` / `billing-forms.test.js`.
**Create routes:** `frontend/src/routes/(app)/settings/legal-entities/{+page.server.js,+page.svelte,new/+page.server.js,new/+page.svelte,[id]/edit/+page.server.js,[id]/edit/+page.svelte}`; `invoices/[id]/edit/{+page.server.js,+page.svelte}`; `invoices/acts/{+page.server.js,+page.svelte,new/+page.server.js,new/+page.svelte,[id]/+page.server.js,[id]/+page.svelte,[id]/edit/+page.server.js,[id]/edit/+page.svelte,[id]/pdf/+server.js}` под тем же `(app)`; `routes/api/billing/legal-entities/[id]/scans/[kind]/+server.js` proxy.
**Create components:** `frontend/src/lib/v2/components/billing/{LegalEntityFields,CustomerBillingFields,DocumentPartyFields,ServicePeriodFields,UATotals,ActLinesEditor}.svelte`.
**Modify:** `lib/server/v2/{invoices,accounts}.js` и tests; `lib/v2/components/{Sidebar,LineItemsEditor}.svelte`; `routes/(app)/settings/+page.svelte` (ссылка на справочник); `routes/(app)/invoices/{new/+page.server.js,new/+page.svelte,+page.server.js,+page.svelte,[id]/+page.server.js,[id]/+page.svelte,[id]/pdf/+server.js}`; `routes/(app)/accounts/{new/+page.server.js,new/+page.svelte,[id]/edit/+page.server.js,[id]/edit/+page.svelte,[id]/+page.server.js,[id]/+page.svelte}`. Учитывать текущую параллельную работу в этих файлах.
**Interfaces:** методы JS `listLegalEntities/getLegalEntity/saveLegalEntity`, `listActs/getAct/createAct/updateAct/issueAct/cancelAct`, `issueInvoice/updateInvoice` поверх cookie-aware apiRequest; exact JSON §2.4. Следовать текущему UI, не создавать редизайн всего приложения.

- [ ] RED JS: mapping сохраняет decimal strings/8-digit quantity; все обязательные реквизиты отправляются; snapshot read-only; hidden404/validation400/stale409 различаются; списки не теряют фильтры; исходные scan bytes не попадают в page data. Unit tests helper/action modules не импортируют `.svelte` и не требуют новых DOM-харнесов.
- [ ] Run RED: `cd frontend && pnpm exec vitest run src/lib/server/v2/legal-entities.test.js src/lib/server/v2/service-acts.test.js src/lib/server/v2/billing-forms.test.js src/lib/server/v2/invoices.test.js src/lib/server/v2/accounts.test.js`.
- [ ] Реализовать формы реквизитов, выбор активной компании и её банков, клиент/плательщик по умолчанию один, договор/период, unit, read-only суммы с отдельным ПДВ, preview/issue и 2 PDF ссылки. Act editor из invoice предлагает только оставшиеся строки, «весь остаток» точной строкой, серверный конфликт показывается без потери ввода.
- [ ] Добавить список актов и связь из invoice/account; paid/closed/remaining отдельными величинами, не суммировать валюты generic invoice в общий гривневый итог. UA draft может сохраняться без нового периода; перед выпуском требуется выбрать и проверить период. У редактируемого UA draft есть Edit, у выпущенного нет. Для повторного счёта кнопка duplicate открывает новый draft с новым периодом и без старых оплат/актов/архивов.
- [ ] GREEN JS те же tests; `pnpm check`; затем настоящая browser QA по T7. Маршрут settings/+page.svelte проверен и существует; добавить ссылку на новые настройки, сохранив текущие ссылки.

### Task 6: Все существующие пути Invoice и совместимость

**Depends:** T5 (backend service может проверяться после T4, финальный сценарий — после UI). **Результат:** ни один существующий путь не обходит новые правила и не меняет старую семантику.

**Create:** `backend/invoices/tests/test_ua_existing_paths.py`; frontend test расширения `invoices.test.js`; при необходимости `mobile/test/unit/ua_invoice_compatibility_test.dart` только на чтение/статусы, без редактора.
**Modify:** `backend/invoices/{models,api_views,serializer,pdf,tasks,public_views,admin}.py`, `backend/cases/services/billing.py` только если требуется общий entrypoint, `frontend/src/lib/server/v2/invoices.js`.
**Interfaces:** generic contract остаётся; new UA duplicate — active issuer/bank selection validated, dates/period не выдаются за новые автоматически, issued_at/snapshot/pdf/payments/acts не копируются. Контакты остаются существующим CRM-полем, реквизиты сторон берутся из Account/draft snapshots, не из Contact email/name вместо юрлица.

- [ ] RED matrix: InvoiceSendView UA до issue400/послеissue использует архив; InvoiceMarkPaidView и PaymentListView UA доissue400; ordinary invoices сохраняют существующие допустимые действия. PublicInvoiceView/PublicInvoicePDFView UA404, ordinary портал работает.
- [ ] RED matrix: InvoiceDuplicateView копирует issuer/договор/unit и fresh draft; EstimateConvertView, InvoiceFromOpportunityView, InvoiceFromTimeEntriesView и recurring `_generate_one` без явного issuer продолжают создавать generic документы. UA возможно получить только явным выбором при создании; не включать issuer автоматически в старые creators. Прямой payment create/delete не меняет архив/closed; issue без email → оплата → удаление последней оплаты оставляет issued_at/номер/PDF неизменными и статус Sent либо Overdue, не Draft; overdue sweep не меняет billed snapshot.
- [ ] RED: UA nested/standalone lines/admin не обходят freeze; публичный Serializer не выдаёт snapshot/archive/scans; email архива чистый; изменение компании или деактивация не изменяет старые PDF, но запрещает новый счёт от архивной компании.
- [ ] Run RED/GREEN: `cd backend && uv run pytest --no-cov invoices/tests/test_ua_existing_paths.py invoices/tests/ accounts/tests/ -q`; frontend `pnpm exec vitest run src/lib/server/v2/invoices.test.js src/lib/server/v2/accounts.test.js`. Для mobile при изменении wire-parser выполнить его существующие тесты; новая функциональность UI туда не добавляется.

### Task 7: Реальная PostgreSQL-проверка, печать и приёмка

**Depends:** T6. **Результат:** доказательства A1–A9, готовая документация и отчёт об ограничениях, без deployment.

**Create:** `backend/invoices/tests/test_ua_rls.py` (postgres_only); при необходимости `frontend/src/lib/server/v2/billing-pdf-proxy.test.js` (чистый helper для proxy). **Modify docs:** `docs/api/invoices.md`, `docs/contributing/testing.md` (только обнаруженная устаревшая PG-инструкция), `docs/self-hosting/backups-and-upgrades.md` (существует) и новый `docs/self-hosting/billing-documents.md`, включить страницу в `mkdocs.yml`; `.github/workflows/tests.yml` package-build job для новых UA resources smoke. `schema.yml` обновлять только штатной генерацией Spectacular, не вручную.

- [ ] Из CI и `crm/test_settings_postgres.py` взять env подключения к отдельной disposable PostgreSQL test DB; никакой production DSN. Секреты не печатать. Role для postgres_only — NOSUPERUSER NOBYPASSRLS, умеет создавать тестовую БД. Подготовку роли выполнять только в локальном/CI тестовом окружении.
- [ ] RED/GREEN PostgreSQL: включить все новые таблицы FORCE RLS, проверить pg_policies/relforcerowsecurity и реальный select/insert/update с пустым/правильным/чужим Org. `rls_org` и `set_rls_context` из текущих testing helpers; учитывать per-thread context в гонках. Нет superuser-фиктивной проверки RLS.
- [ ] Из `backend/`, с тестовыми DB env: `DJANGO_SETTINGS_MODULE=crm.test_settings_postgres uv run pytest --no-cov -q -m postgres_only invoices/tests/test_ua_rls.py invoices/tests/test_ua_act_races.py invoices/tests/test_ua_numbering.py`. Assertions: два разных документа получают разные номера, повтор issue не выдаёт второй, два полных закрытия не проходят, отмена/issue одной строки согласованы. Отдельно `DJANGO_SETTINGS_MODULE=crm.test_settings_postgres uv run pytest --no-cov -q -m 'not postgres_only' invoices/tests/ accounts/tests/` для типов/constraints.
- [ ] MigrationExecutor на disposable PostgreSQL: начать до new migrations, проверить generic preserved/номера, применить new schema+RLS, создать несколько компаний и одинаковые печатные номера между ними. Reverse допускается только без созданных UA данных: после UA документов rollback приложения без удаления данных, не пытаться вернуть unconditional org-number constraint на live набор с повторяющимися номерами.
- [ ] Из `backend/`: `DJANGO_SETTINGS_MODULE=crm.test_settings uv run python manage.py makemigrations --check --dry-run`; `DJANGO_SETTINGS_MODULE=crm.test_settings uv run pytest -q -m 'not postgres_only'` (с configured coverage, итог ≥50%, записать процент/базовые сбои); `uv run ruff check .`; `uv run ruff format --check .`. Из `frontend/`: `pnpm test`; `pnpm eslint .`; `pnpm check`; `pnpm build`; Prettier check изменённых frontend файлов. Прежние сбои отдельно baseline, не скрывать и не исправлять постороннее.
- [ ] Installed-wheel smoke по существующему package-build job: из backend выполнить `uv build --wheel --out-dir <temporary-dir>/dist`, создать отдельную временную venv, установить полученный wheel и запускать Python из neutral cwd вне checkout. Импортировать invoices.billing, проверить packaged invoice.html/act.html/CSS/font/LICENSE через importlib.resources и отрендерить два синтетических snapshot настоящим WeasyPrint с packaged font. Добавить эту же проверку в `.github/workflows/tests.yml:package-build`, чтобы CI проверял runtime ресурсы; ничего не публиковать и не использовать editable source вместо wheel.
- [ ] Browser acceptance на синтетических данных: создать3 компании, банки/сканы; карточку клиента; годовой UA счёт с ПДВ и NON_PAYER; preview, issue без email; получить оба PDF; частичный/финальный акт; оплатить независимо; отменить акт и закрыть остаток заново; monthly duplicate без старого периода; member/hidden и409 сценарии. Сетевой запрос → API → сохранённые данные → UI/PDF проверяются совместно, не только screenshots.
- [ ] Render реальных PDF в PNG, inspect: одна/много страниц, длинные названия/адреса, кириллица, переносы строк, таблицы и повторы заголовков, даты/периоды/реквизиты обеих сторон, net/VAT/gross/пропись, сканы без обрезки и только нашей стороны. Сверить поля с образцами, не копируя реальные данные. Архивный SHA после смены реквизитов/шаблона/оплаты остаётся прежним.
- [ ] Документировать API/lifecycle, ограничения UA/перенос номеров/резервное копирование DB со сканами и архивами, инструкции печати, mapping A1–A9. Генерация схемы: `DJANGO_SETTINGS_MODULE=crm.test_settings uv run python manage.py spectacular --file ../schema.yml --validate`; `uv run --group docs mkdocs build --strict -f ../mkdocs.yml -d /tmp/ua-billing-docs-site`.
- [ ] Итоговый diff review и `git diff --check`, отчёт фактически выполненных проверок и ограничения. Не коммитить/мержить/деплоить без отдельного запроса. Завершить реализацию только после всех доступных required gates; отсутствие PG/WeasyPrint/browser отмечать как непроверенный критерий, не зелёный результат.

## 4. Приёмка, порядок внедрения и остаточные решения

| Критерий | Задачи | Доказательство |
|---|---|---|
| A1: несколько компаний/банков | T1/T2/T5 | allow/deny API + browser3 компании |
| A2: ПДВ/Без ПДВ/пропись | T2/T3 | точные Decimal fixtures + PDF text/visual |
| A3: частичные/месячные документы | T4/T5 | q12/q1 годовые примеры + manual duplicate |
| A4: остатки и гонки | T4/T7 | PostgreSQL concurrent + copy totals to cent |
| A5: архивы/сканы | T1/T3/T7 | hash invariance + visual2 вариантов |
| A6: номера | T2/T3/T4/T7 | conditional unique + concurrent issue |
| A7: доступ/RLS | T1/T4/T7 | hidden404 + non-superuser DB tests |
| A8: существующие потребители | T6 | compatibility matrix + старые suites |
| A9: реальная печать/UI | T5/T7 | browser, render PDF, documented limitations |

Порядок будущего внедрения: additive schema/RLS → backend services/API → UI → acceptance на staging → отдельное разрешение на production. Никакого автоматического backfill/старой истории в новый финансовый модуль. До первых реальных документов оператор проверяет реквизиты, префиксы и ставку. Не делать destructive rollback после выпуска документов: сохранять новую схему/архивы и исправлять вперёд.

Материальные ограничения, открытые честно:

- Пользователь утвердил функциональный состав в чате; binary storage, нумерация без yearly reset, initial UA без скидок/shipping/foreign currency и 8-digit fractions — предлагаемые технические решения этого плана, их можно скорректировать при его чтении до реализации. Нет нерешённой задачи, вынуждающей менять код сейчас.
- Для реализации нужны реальные isolated PostgreSQL/WeasyPrint/browser окружения; сейчас они не запускались, тесты будущей функции не исполнялись.
- Формы исходят из примеров обычных услуг; отраслевые/налоговые требования вне объёма. Налоговая классификация продуктов задаётся оператором, программа не определяет её по названию.
- Данные/сканы в БД увеличивают backup; сканы ≤2MiB и PDF ≤10MiB каждый ограничивают размер. Отдельное объектное хранилище не требуется для первой версии.
- Наличие параллельных frontend изменений требует повторной сверки файлов перед исполнением и аккуратного узкого применения.

## 5. Аудит плана

Результат независимых осей, подтверждённые исправления, повторные проверки и состояние дерева будут записаны в [журнал аудита](2026-10-15-ukrainian-billing-audit.md). Готовность плана не означает выполненную или проверенную реализацию.
