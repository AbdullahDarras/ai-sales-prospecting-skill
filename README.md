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

**Claude Code** (إضافة من المنتج):
```
/plugin marketplace add AbdullahDarras/ai-sales-prospecting-skill
/plugin install sales-prospecting@ai-sales-prospecting
```

**أي وكيل يدعم Agent Skills** (أمر `skills`):
```bash
npx skills add AbdullahDarras/ai-sales-prospecting-skill            # أو أضف -a codex / -a claude-code / -a gemini-cli
```

**يدويًا:** انسخ المجلد `skills/sales-prospecting` إلى مجلد المهارات عند وكيلك:
```bash
git clone https://github.com/AbdullahDarras/ai-sales-prospecting-skill
cp -R ai-sales-prospecting-skill/skills/sales-prospecting ~/.claude/skills/     # Claude Code (عام)
cp -R ai-sales-prospecting-skill/skills/sales-prospecting ~/.agents/skills/     # Codex CLI وغيره (عام)
cp -R ai-sales-prospecting-skill/skills/sales-prospecting .gemini/skills/       # Gemini CLI (داخل المشروع)
```
وكيل بلا دعم أصلي للمهارات؟ افتح هذا المستودع داخله: يقرأ `AGENTS.md` أو `GEMINI.md` ويتبع `SKILL.md`.

> المسارات أعلاه حسب معيار Agent Skills. راجع توثيق وكيلك إن اختلف عندك.

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
```
# Claude Code
/plugin marketplace add AbdullahDarras/ai-sales-prospecting-skill
/plugin install sales-prospecting@ai-sales-prospecting

# any Agent Skills-compatible agent
npx skills add AbdullahDarras/ai-sales-prospecting-skill     # add -a codex | -a claude-code | -a gemini-cli

# manual: copy skills/sales-prospecting into your agent's skills folder
#   Claude Code: ~/.claude/skills/   Codex etc.: ~/.agents/skills/   Gemini CLI: .gemini/skills/
```
Agents without native skill support: open this repo in the agent; it reads `AGENTS.md` / `GEMINI.md` and follows `SKILL.md`.

**Use:** ask your agent, e.g. *"Find 5 independent cafes in Riyadh that match my ICP and draft outreach."*
It asks for the segment plus your sender and company names (used in the message signature), then runs the workflow.
Add your own segments as YAML (`references/icp-authoring.md`); three examples are bundled.

**Know the limits** ([`limitations.md`](skills/sales-prospecting/references/limitations.md)): on real tests no lead
passed the automatic readiness thresholds (public data rarely proves owners, maps status or last post), thresholds are
provisional until calibrated with your best past customers, and Maps/Instagram are usually unreadable logged-out.
Message rules are Arabic-specific. You are responsible for platform terms and data-protection law, and for honouring opt-outs.

**License:** MIT.
