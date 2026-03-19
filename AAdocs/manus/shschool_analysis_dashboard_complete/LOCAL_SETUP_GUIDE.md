# دليل تشغيل لوحة تحليل SHSchool محلياً

## المتطلبات الأساسية

قبل البدء، تأكد من تثبيت البرامج التالية على جهازك:

### 1. **Node.js و npm** (أو pnpm)
- **تحميل Node.js**: https://nodejs.org/ (اختر LTS)
- **التحقق من التثبيت**:
  ```bash
  node --version
  npm --version
  ```

### 2. **Git** (اختياري لكن مفيد)
- **تحميل Git**: https://git-scm.com/
- **التحقق من التثبيت**:
  ```bash
  git --version
  ```

### 3. **محرر نصوص** (مثل VS Code)
- **تحميل VS Code**: https://code.visualstudio.com/

---

## خطوات التثبيت والتشغيل

### الخطوة 1: تحميل المشروع

#### الطريقة الأولى: من خلال الملف المضغوط
1. قم بتحميل ملف المشروع `shschool_analysis_dashboard.zip`
2. فك الضغط عن الملف في المجلد المطلوب

#### الطريقة الثانية: باستخدام Git (إذا كان متاحاً)
```bash
git clone <repository-url>
cd shschool_analysis_dashboard
```

### الخطوة 2: تثبيت المكتبات المطلوبة

افتح Terminal/Command Prompt في مجلد المشروع وقم بتنفيذ:

```bash
# استخدام npm
npm install

# أو استخدام pnpm (أسرع)
pnpm install

# أو استخدام yarn
yarn install
```

**ملاحظة**: هذه الخطوة قد تستغرق عدة دقائق حسب سرعة الإنترنت.

### الخطوة 3: تشغيل خادم التطوير

بعد انتهاء التثبيت، قم بتشغيل الخادم:

```bash
# استخدام npm
npm run dev

# أو استخدام pnpm
pnpm dev

# أو استخدام yarn
yarn dev
```

### الخطوة 4: فتح المشروع في المتصفح

بعد تشغيل الخادم، ستظهر رسالة مشابهة لهذه:

```
➜  Local:   http://localhost:3000/
➜  Network: http://192.168.x.x:3000/
```

افتح المتصفح وانتقل إلى: **http://localhost:3000/**

---

## هيكل المشروع

```
shschool_analysis_dashboard/
├── client/
│   ├── public/              # الملفات الثابتة (favicon, robots.txt)
│   ├── src/
│   │   ├── pages/          # الصفحات الرئيسية
│   │   │   ├── Home.tsx           # الصفحة الرئيسية
│   │   │   ├── SWOTDetail.tsx     # تحليل SWOT
│   │   │   ├── ComplianceDetail.tsx # الامتثال
│   │   │   ├── SecurityDetail.tsx   # الأمان
│   │   │   └── Roadmap.tsx         # خارطة الطريق
│   │   ├── components/     # المكونات المعاد استخدامها
│   │   │   ├── ArchitectureFlowchart.tsx
│   │   │   └── DataFlowDiagram.tsx
│   │   ├── App.tsx         # التطبيق الرئيسي
│   │   ├── main.tsx        # نقطة الدخول
│   │   └── index.css       # الأنماط العامة
│   └── index.html          # ملف HTML الرئيسي
├── package.json            # المكتبات والمتطلبات
└── README.md              # ملف التوثيق
```

---

## الصفحات المتاحة

بعد التشغيل، يمكنك الوصول إلى الصفحات التالية:

| الصفحة | الرابط | الوصف |
|--------|--------|-------|
| الرئيسية | `http://localhost:3000/` | نظرة عامة على التحليل |
| تحليل SWOT | `http://localhost:3000/swot` | تحليل تفصيلي SWOT |
| الامتثال | `http://localhost:3000/compliance` | تقييم الامتثال القانوني |
| الأمان | `http://localhost:3000/security` | تقييم الأمان التفصيلي |
| خارطة الطريق | `http://localhost:3000/roadmap` | الجدول الزمني والمراحل |

---

## الأوامر المفيدة

### تطوير وتصحيح الأخطاء

```bash
# تشغيل خادم التطوير مع إعادة تحميل تلقائية
npm run dev

# فحص أخطاء TypeScript
npm run check

# تنسيق الكود
npm run format

# بناء المشروع للإنتاج
npm run build

# معاينة النسخة المُنتجة
npm run preview
```

### إيقاف الخادم

اضغط **Ctrl + C** في Terminal لإيقاف الخادم.

---

## استكشاف الأخطاء

### المشكلة: "npm: command not found"
**الحل**: تأكد من تثبيت Node.js بشكل صحيح. أعد تثبيت Node.js من https://nodejs.org/

### المشكلة: "Port 3000 is already in use"
**الحل**: الخادم يعمل بالفعل على المنفذ 3000. إما أغلق البرنامج الآخر أو غيّر المنفذ:
```bash
# تغيير المنفذ (مثال: 3001)
PORT=3001 npm run dev
```

### المشكلة: "Module not found"
**الحل**: أعد تثبيت المكتبات:
```bash
rm -rf node_modules package-lock.json
npm install
```

### المشكلة: الصفحة لا تحمل بشكل صحيح
**الحل**: امسح ذاكرة التخزين المؤقت للمتصفح:
- اضغط **Ctrl + Shift + Delete** (أو **Cmd + Shift + Delete** على Mac)
- اختر "Clear browsing data"
- أعد تحميل الصفحة

---

## التطوير والتخصيص

### تعديل الألوان والأنماط

قم بتعديل ملف `client/src/index.css` لتغيير الألوان والأنماط العامة:

```css
:root {
  --primary: var(--color-blue-700);
  --background: oklch(1 0 0);
  /* ... الألوان الأخرى */
}
```

### إضافة صفحة جديدة

1. أنشئ ملف جديد في `client/src/pages/NewPage.tsx`
2. أضف المسار في `client/src/App.tsx`:
```tsx
import NewPage from "./pages/NewPage";

// في Router:
<Route path="/new-page" component={NewPage} />
```

### تعديل البيانات

يمكنك تعديل البيانات مباشرة في ملفات الصفحات (مثل `Home.tsx`, `SWOTDetail.tsx`, إلخ).

---

## نصائح مفيدة

1. **استخدم VS Code Extensions**:
   - ES7+ React/Redux/React-Native snippets
   - Tailwind CSS IntelliSense
   - TypeScript Vue Plugin

2. **استخدم React Developer Tools**:
   - تحميل: https://react-devtools-tutorial.vercel.app/
   - يساعد في تصحيح الأخطاء

3. **استخدم Browser DevTools**:
   - اضغط **F12** أو **Ctrl + Shift + I** لفتح أدوات المطور
   - استخدم Console لتصحيح الأخطاء

4. **الحفظ التلقائي**:
   - عند تعديل الملفات، الخادم سيعيد تحميل الصفحة تلقائياً

---

## بناء النسخة الإنتاجية

عندما تكون جاهزاً لنشر المشروع:

```bash
# بناء النسخة الإنتاجية
npm run build

# سيتم إنشاء مجلد "dist" يحتوي على الملفات الجاهزة للنشر
```

---

## الدعم والمساعدة

إذا واجهت أي مشاكل:

1. تحقق من رسائل الخطأ في Terminal
2. تحقق من Browser Console (F12)
3. جرب مسح ذاكرة التخزين المؤقت وإعادة التثبيت
4. تأكد من أن جميع المتطلبات مثبتة بشكل صحيح

---

## معلومات إضافية

- **Framework**: React 19
- **Styling**: Tailwind CSS 4
- **UI Components**: shadcn/ui
- **Routing**: Wouter
- **Charts**: Recharts
- **Language**: TypeScript

---

**تم إعداد هذا الدليل في: 19 مارس 2026**

للمزيد من المعلومات، راجع ملف `README.md` في المشروع.
