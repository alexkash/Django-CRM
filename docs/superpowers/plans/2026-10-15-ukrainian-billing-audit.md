# Аудит плана украинских счетов и актов

Дата: 2026-10-15. Режим: **create and review** по phased-plan-review. Только документы, без реализации, коммитов или внешних действий.

## Вход и артефакты

- Источник: обсуждение владельца проекта — одна CRM, наши ФОП/ТОВ, ручные счета и частичные акты, отдельный ПДВ, PDF со сканами, автоматизация позже; предоставленные XLSM и PDF использованы как образцы полей.
- [Дерево и требования](../specs/2026-10-15-ukrainian-billing-design.md).
- [План реализации](2026-10-15-ukrainian-billing.md).
- Исследован существующий код, тесты, settings, CI, CONTRIBUTING, применимые AGENTS.md. HEAD при обследовании `f3f9053a`, ветка `alexkash/install`. Чужие рабочие изменения сохранены; точный состав дерева меняется параллельно.

## Метод

Три независимых read-only ревьюера проверили: (A) correctness/repository facts, (B) architecture/scope/simplicity, (C) decomposition/testing/execution readiness. Координатор проверил каждое замечание по коду и требованиям, объединил только дубли одной причины. Ревьюеры не редактировали код и не запускали реализацию.

## Подтверждённые замечания первого прохода

| ID | Severity | Проблема и доказательство | Исправление плана |
|---|---|---|---|
| F1 | MAJOR | Независимое округление каждой месячной доли от исходных0.07 грн расходует денежный бюджет раньше количества: 7 ×0.01 уже0.07, но q закрыто только0.58333331. Первоначальная spec §4.3. | Перераспределение из оставшихся q/net/VAT при каждом выпуске, последняя часть равна точному остатку; tests tiny amount, VAT exhaustion, cancel/reissue. Spec §4.3, plan §2.1/T4. |
| F2 | MAJOR | `_next_number` сканирует все Invoice и Cast suffix в integer (`backend/invoices/models.py:284–287`); произвольный новый префикс может ломать обычный Invoice. Найден независимо A/B, один дефект. | Ordinary Invoice allocator фильтрует issuer IS NULL; Estimate/прочие consumers unchanged. Numeric/nonnumeric overlapping prefixes проверяются на PostgreSQL. Spec §4.2, plan §2.3/T2/T6. |
| F3 | MAJOR | Serializer exclusion не исключает BinaryField из SQL. InvoiceListView выбирает полные rows (`invoices/api_views.py:171–184`), CSV чанки могут включить сотни архивов (`common/csv_export.py:158–174`). | Default defer binary fields + explicit binary loaders; related/CSV/workers audit; query-level projection regression. Spec §4.4, plan §2.3/T2. |
| F4 | MAJOR | UA issue не выставляет sent_at; `Payment.update_invoice_payment` после удаления последней оплаты возвращает Draft по отсутствию sent_at (`invoices/models.py:813–823`). | UA unpaid status выводится из issued_at →Sent/Overdue; generic branch сохраняется. Regression issue(no email)→payment→delete-last + invariant number/hash/closure. Spec §4.4, plan §2.2/T6. |
| F5 | MAJOR | Все запланированные backend команды использовали --no-cov, обходя обязательные50% (`AGENTS.md`, `.coveragerc:59`, `backend/pytest.ini`). | Финальный SQLite прогон с configured coverage ≥50%; focused/PG остаются без coverage; процент и baseline limitations фиксируются в отчёте. Plan T7. |
| F6 | MINOR | Runtime UA templates/font/CSS/license проверялись только из checkout; существующий package-build smoke (`.github/workflows/tests.yml:266–303`) не проверяет новые ресурсы. | Clean-wheel install в отдельной temporary venv/neutral cwd, чтение ресурсов и настоящий render обоих snapshot; добавить шаг существующему CI package-build. Plan T7. |

Подтверждено 6 уникальных замечаний (5 MAJOR, 1 MINOR), все включены в исправления. Неподтверждённых или отклонённых кандидатов первого прохода нет. Дубли F2 не считаются отдельными дефектами. Архитектурный reviewer использовал сокращённую маркировку severity; координатор классифицировал формальные записи, не трактовал их как clean response.

Дополнительно координатор уточнил: черновик может быть неполным до issue; период акта внутри периода счёта; у ServiceAct есть immutable issuer FK для DB uniqueness; actor service contract и money dataclasses названы; ранние T1 тесты не зависят от ещё не реализованного акта; фактические пути настроек/backup docs проверены. Это устранение неоднозначностей в документах, не расширение продуктового объёма.

## Повторный критический аудит

Статус: завершён. После исправлений два свежих независимых reviewer прочитали полный текущий план и проверили факты репозитория.

- Correctness / repository facts: **NO FINDINGS**.
- Architecture / scope / simplicity: **NO FINDINGS**.

Выполнены первичный проход трёх осей, один раунд исправлений и один свежий критический повторный проход двух осей. Лимит трёх раундов не потребовался. Неподтверждённых и нерешённых actionable findings не осталось. Итог: план готов к передаче на чтение и последующую реализацию по отдельному запросу; это не утверждение о готовности кода.

## Проверки артефактов

Выполнены при подготовке и финальной проверке документов:

- Проверены существующие modify-paths и реальные pytest/pnpm/PG/CI настройки; найденную устаревшую документацию не использовали вместо кода.
- Проверена арифметика текста плана чистым Decimal-расчётом: q=1, 12 частей (11×0.08333333 + остаток), net/VAT0.07/0.01 и12000/2400: все12 частей в пределах остатка, конечные суммы q/net/VAT совпадают точно. Это проверка формулы в плане, не тест будущей реализации.
- UTF-8, парность fenced blocks, отсутствие trailing whitespace и относительные Markdown links проверены после завершения аудита: все3 документа прошли, отсутствующих локальных ссылок нет.
- `git diff --check` на текущем дереве: exit0, вывод пустой. Для всех3 новых untracked документов дополнительно выполнен `git diff --no-index --check /dev/null <file>`: ошибок whitespace нет.

Тесты будущей функции, Django migrations, dev servers, browser и production не запускались: цель этой задачи — дерево, план и аудит, не доказательство реализованного поведения.

## Состояние и границы результата

Созданы только три документа design/plan/audit. Прикладной код не менялся в рамках этой задачи, существующие и появившиеся параллельно рабочие изменения не трогались. Коммитов этой задачи, push/PR/deployment нет. Во время аудита параллельная работа создала commit `0ba4bde5` (SuiteCRM frontend history); итоговый HEAD — `0ba4bde5`. Diff от исходного `f3f9053a` проверен: backend invoices/accounts/RLS/settings, CI и используемые invoice/account API mapping не изменились; изменения пересекающихся frontend страниц/Sidebar только добавляют history/UAH и сохраняются. Основания аудита остаются применимы. Рабочее дерево не чистое: три новых документа, AGENTS.md и output/; эти посторонние файлы не включались в задачу. Перед реализацией требуется отдельный запрос пользователя; технические решения и ограничения явно указаны в плане.
