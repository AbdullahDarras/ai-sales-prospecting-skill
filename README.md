# AI Sales Prospecting Skill · مهارة اكتشاف العملاء المثاليين

**العربية** · [English](#english)

مهارة (Agent Skill) تعمل مع أي وكيل ذكاء اصطناعي يدعم المهارات: **Claude Code وCodex وGemini CLI** وغيرها.
تجعل الوكيل يبحث عن العملاء المثاليين لنشاطك من مصادر عامة على الإنترنت، ويتحقق من صحة بياناتهم ومن مطابقتهم لفئتك،
ثم يجهّز لكل عميل رسالة تواصل أولى **بانتظار اعتماد إنسان**. لا يرسل شيئًا بنفسه.

## كيف تعمل

الوكيل هو «الدماغ»: يبحث ويحكم بأدواته. والسكربتات «الحارس»: تفرض القواعد حتميًا وتخزّن كل شي.

```
اكتشاف → إثراء → تحقق → تقييم → صياغة → اعتماد بشري → (إرسال: بيدك) → تصدير Excel
```

- **كل معلومة لها مصدر:** معلومة بلا رابط الصفحة التي ظهرت فيها لا تُحفظ.
- **طبقة تحقق:** تطابق الاسم والهاتف بين مصادر مستقلة، صلاحية أرقام الخليج والأردن، نشاط المنشأة، تأكيد صاحب القرار.
- **فلاتر حتمية:** حجم الشركة وعدد الفروع والمنشآت المغلقة والحكومية تُستبعد دون الاعتماد على تقدير النموذج.
- **حكم بلا دليل لا يُصدَّق:** الدرجة العالية التي لا تسندها روابط مخزَّنة تُخفَّض، والحالات الحدّية تمر على مراجِع معاكس.
- **رسائل آمنة:** فصحى رسمية، بدون أي سعر، فيها سطر إلغاء اشتراك، وتُفحص آليًا قبل أن تصلك.
- **شرائح بملفات YAML:** أضف شريحة جديدة بدون تعديل الكود. مرفق ثلاثة أمثلة (عيادات، مطاعم وكافيهات، شركات خدمية).
- **واجهة اعتماد** عربية (من اليمين لليسار، فاتح وداكن) و**تصدير Excel** جاهز لفريق المبيعات.

## التثبيت

### من داخل تطبيق Claude Desktop، بدون طرفية (الأسهل)

1. افتح تطبيق **Claude** واذهب إلى تبويب **Code**، وابدأ جلسة جديدة (بأي مجلد).
2. الصق هذه الجملة وأرسلها:

```
ثبّت لي مهارة sales-prospecting. نفّذ التعليمات الموجودة في هذا الملف حرفيًا:
https://raw.githubusercontent.com/AbdullahDarras/ai-sales-prospecting-skill/main/INSTALL.md
```

3. سيطلب Claude إذنك لتشغيل أوامر (تنزيل المستودع، نسخ المجلد، تجهيز بيئة بايثون). اقرأها ووافق.
4. عند انتهائه افتح **جلسة جديدة** (الجلسة الحالية لا ترى المهارة)، وقل مثلًا:
   «ابحث لي عن 5 كافيهات مستقلة في الرياض وجهّز رسائل التواصل».

يعمل على ماك وLinux ويحتاج Python 3.9 أو أحدث (الماك الجديد يعرض تثبيته تلقائيًا) واتصال إنترنت.
المهارة تُنسخ إلى `~/.claude/skills/` الذي تقرأه جلسات Code المحلية في التطبيق
([التوثيق](https://code.claude.com/docs/en/desktop#use-skills)).
> الظهور في زر **+ ← Plugins ← Add plugin** غير متاح حاليًا: ذلك المتصفح يعرض إضافات المنتجات المضافة مسبقًا ومنتج Anthropic فقط.

### بالطرفية (Claude Code، ويشتغل أيضًا مع التطبيق وVS Code)

افتح **الطرفية (Terminal)** على جهازك (وليس خانة المحادثة داخل التطبيق)، وشغّل:

```bash
claude plugin marketplace add AbdullahDarras/ai-sales-prospecting-skill
claude plugin install sales-prospecting@ai-sales-prospecting
```

ثم ابدأ جلسة جديدة. الإضافة تظهر كذلك بتبويب **Code** في تطبيق Claude Desktop وفي VS Code لأنها تقرأ نفس الإعدادات.
الأمر `claude` يأتي من [Claude Code](https://code.claude.com/docs/en/overview) (إن لم يكن عندك، استخدم «يدويًا» بالأسفل).

> **رسالة «Plugins aren't available in this environment»؟** تظهر إذا كتبت `/plugin ...` داخل تبويب Code بتطبيق Desktop أو VS Code أو claude.ai/code.
> هذا متوقع: أوامر `/plugin` تعمل فقط داخل جلسة `claude` بالطرفية. استخدم أوامر `claude plugin ...` أعلاه من الطرفية.
> وإذا كنت أصلًا داخل جلسة `claude` بالطرفية، يكفي أمر واحد: `/plugin install sales-prospecting --marketplace AbdullahDarras/ai-sales-prospecting-skill` (يحتاج إصدار 2.1.275 أو أحدث).
> الجلسات السحابية (claude.ai/code) لا تحمّل الإضافات المثبتة على جهازك.

### يدويًا (بدون أوامر الإضافات)

```bash
git clone https://github.com/AbdullahDarras/ai-sales-prospecting-skill
mkdir -p ~/.claude/skills
cp -R ai-sales-prospecting-skill/skills/sales-prospecting ~/.claude/skills/
```
بدون git: من صفحة المستودع اضغط **Code ← Download ZIP**، فك الضغط، وانسخ المجلد `skills/sales-prospecting` إلى `~/.claude/skills/`
(في Finder: ‏`Cmd+Shift+G` ثم اكتب `~/.claude/skills`). ثم ابدأ جلسة جديدة.

### وكلاء آخرون (Agent Skills)

```bash
npx skills add AbdullahDarras/ai-sales-prospecting-skill            # أو أضف -a codex / -a gemini-cli
```
أو انسخ `skills/sales-prospecting` إلى: ‏`~/.agents/skills/` (Codex وغيره) أو `.gemini/skills/` (Gemini CLI داخل المشروع).
وكيل بلا دعم أصلي للمهارات؟ افتح هذا المستودع داخله: يقرأ `AGENTS.md` أو `GEMINI.md` ويتبع `SKILL.md`.
> هذه المسارات حسب معيار Agent Skills. راجع توثيق وكيلك إن اختلف عندك.

## الاستخدام

بعد التثبيت اطلب من وكيلك بلغتك الطبيعية، مثل:

> «ابحث لي عن 5 كافيهات مستقلة في الرياض تناسب شريحتي، وجهّز رسائل التواصل.»

سيسألك عن الشريحة واسمك واسم شركتك (يظهران بتوقيع الرسائل)، ثم يمشي بالخطوات. لمراجعة النتائج:

```bash
python3 skills/sales-prospecting/scripts/sales_cli.py --workspace ./sales-workspace serve     # واجهة الاعتماد على 127.0.0.1
python3 skills/sales-prospecting/scripts/sales_cli.py --workspace ./sales-workspace export-xlsx
```

كل الأوامر موثقة في [`references/cli-reference.md`](skills/sales-prospecting/references/cli-reference.md).
بياناتك تبقى في `./sales-workspace` على جهازك (وتُستبعد من git).

## حدود يجب أن تعرفها

اختُبرت على بيانات حقيقية (الخليج، عيادات ومطاعم وشركات خدمية). اقرأ
[`limitations.md`](skills/sales-prospecting/references/limitations.md). أهمها:
- لم يجتز عميل واحد العتبة الآلية للجاهزية في الاختبارات. المصادر العامة نادرًا تثبت المالك أو حالة الخرائط أو آخر منشور،
  فتوقع أن أغلب العملاء الجيدين يصلون «غير محسوم» لتحكم عليهم أنت.
- العتبات (تحقق 75 وملاءمة 70) مبدئية. عايرها بأفضل عملائك السابقين قبل الاعتماد عليها.
- خرائط جوجل وإنستغرام بدون تسجيل دخول غالبًا لا يقرؤها الوكيل.
- **المسؤولية القانونية عليك:** احترم شروط المنصات وأنظمة حماية البيانات في بلدك وبلد العميل، وأوقف التواصل لمن يطلب ذلك.

## التطوير

```bash
pip install pyyaml openpyxl fastapi uvicorn pytest httpx
pytest
```
اختبارات تشمل محاكاة وكيل كامل عبر الـCLI، وحارس يمنع تسرب مسارات شخصية أو بيانات أو خطوط للمستودع.
الخط في الواجهة اختياري: ضع ملفات OTF في `scripts/sales_agent/web/static/fonts/` (غير مرفقة بسبب الترخيص).

---

## English

An **Agent Skill** that works with any agent supporting the open Agent Skills format: **Claude Code, Codex,
Gemini CLI** and others. It makes the agent find ideal customers from public web sources, verify their data,
check fit against your ICP, and prepare first-contact messages **for human approval**. It never sends anything.

**How:** the agent is the brain (it searches and judges with its own tools); the scripts are the guard
(deterministic scoring, exclusions, source enforcement, message checks, SQLite storage, Excel export, approval UI).

```
discover → enrich → verify → score → draft → human approval → (sending: yours) → Excel export
```

**Install**

*Inside the Claude Desktop app, no terminal (easiest).* In the **Code** tab start a new session and paste:
```
Install the sales-prospecting skill. Follow the instructions in this file literally:
https://raw.githubusercontent.com/AbdullahDarras/ai-sales-prospecting-skill/main/INSTALL.md
```
Approve the commands Claude asks to run, then start a **new session**. It copies the skill to `~/.claude/skills/` (loaded by local
Code-tab sessions) and prepares an isolated Python environment (macOS/Linux, Python 3.9+, internet needed once).

*Claude Code (also covers the Claude Desktop Code tab and VS Code).* Run these in a regular **terminal** (not in the chat box):
```bash
claude plugin marketplace add AbdullahDarras/ai-sales-prospecting-skill
claude plugin install sales-prospecting@ai-sales-prospecting
```
Then start a new session. If you type `/plugin ...` inside the Desktop app's Code tab, VS Code, or claude.ai/code you get
*"Plugins aren't available in this environment"*: that is expected, `/plugin` only works inside a `claude` session in a
terminal ([docs](https://code.claude.com/docs/en/plugins/install)). Inside a terminal session you can also run
`/plugin install sales-prospecting --marketplace AbdullahDarras/ai-sales-prospecting-skill` (v2.1.275+).

*Manual (no plugin commands):*
```bash
git clone https://github.com/AbdullahDarras/ai-sales-prospecting-skill
mkdir -p ~/.claude/skills && cp -R ai-sales-prospecting-skill/skills/sales-prospecting ~/.claude/skills/
```
*Other Agent Skills-compatible agents:* `npx skills add AbdullahDarras/ai-sales-prospecting-skill` (add `-a codex` or `-a gemini-cli`),
or copy `skills/sales-prospecting` into `~/.agents/skills/` (Codex etc.) or `.gemini/skills/` (Gemini CLI).
Agents without native skill support: open this repo in the agent; it reads `AGENTS.md` / `GEMINI.md` and follows `SKILL.md`.

**Use:** ask your agent, e.g. *"Find 5 independent cafes in Riyadh that match my ICP and draft outreach."*
It asks for the segment plus your sender and company names (used in the message signature), then runs the workflow.
Add your own segments as YAML (`references/icp-authoring.md`); three examples are bundled.

**Know the limits** ([`limitations.md`](skills/sales-prospecting/references/limitations.md)): on real tests no lead
passed the automatic readiness thresholds (public data rarely proves owners, maps status or last post), thresholds are
provisional until calibrated with your best past customers, and Maps/Instagram are usually unreadable logged-out.
Message rules are Arabic-specific. You are responsible for platform terms and data-protection law, and for honouring opt-outs.

**License:** MIT.
