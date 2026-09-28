#!/usr/bin/env node
// يبني مشغِّلَ القراءة الجاهز للّصق في javascript_tool على تبويب الصندوق — عملٌ حتميٌّ يتكرّر كلَّ صباح.
// الخطوات: اختبارُ البوّابة أوّلاً (فشلٌ واحدٌ يوقف كلَّ شيء) ← gate.js + runner_tail.js داخل async IIFE
// ← حقنُ SEEN من ledger.json في سطر التعريف نفسِه ← فحصُ الصياغة ← كتابةُ الملفّ.
// لماذا الحقنُ بالسطر كاملاً: «__SEEN__» يرد مرّتين (تعليقٌ ثمّ تعريف)، و replace الساذجُ يغيّر التعليقَ
// ويترك التعريفَ حرفيّاً فيفشل المشغِّل في الصفحة.
// لا يلمس شبكةً ولا صفحة، ولا يطبع أرقامَ التذاكر ولا أيَّ نصّ.
//
// الاستعمال: node build_runner.js [--tools <مجلّد الأدوات>] [--out <ملفّ المخرج>]
// الافتراض: --tools ~/feedback_intake_work  --out <tools>/runner_ready.js

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const TICKET_RE = /^SOS-\d{8}-[0-9A-F]{4}$/;
const SEEN_DECL = 'const SEEN = __SEEN__;';

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function fail(msg) {
  console.error('توقّف: ' + msg);
  process.exit(1);
}

const tools = path.resolve(arg('--tools', path.join(os.homedir(), 'feedback_intake_work')));
const out = path.resolve(arg('--out', path.join(tools, 'runner_ready.js')));

for (const f of ['gate.js', 'runner_tail.js', 'test.js', 'ledger.json']) {
  if (!fs.existsSync(path.join(tools, f))) fail('لا يوجد ' + f + ' في ' + tools);
}

// ١) اختبارُ البوّابة ببياناتٍ اصطناعيّة — بلا نجاحٍ كاملٍ لا قراءة.
const t = spawnSync(process.execPath, ['test.js'], { cwd: tools, encoding: 'utf8' });
const fails = (t.stdout || '').split('\n').filter((l) => l.startsWith('FAIL')).length;
if (t.status !== 0) fail('test.js فشل (' + fails + ' حالة) — أصلح البوّابة قبل القراءة');

// ٢) التذاكرُ المفروزة من ledger.json — مفاتيحُ tickets وحدها، وكلٌّ بصيغة التذكرة.
let seen;
try {
  seen = Object.keys(JSON.parse(fs.readFileSync(path.join(tools, 'ledger.json'), 'utf8')).tickets || {});
} catch (e) {
  fail('ledger.json غيرُ صالح: ' + e.message);
}
const bad = seen.filter((k) => !TICKET_RE.test(k));
if (bad.length) fail(bad.length + ' مفتاحاً في tickets ليس بصيغة SOS-YYYYMMDD-XXXX');

// ٣) التجميعُ والحقن.
const tail = fs.readFileSync(path.join(tools, 'runner_tail.js'), 'utf8');
const hits = tail.split(SEEN_DECL).length - 1;
if (hits !== 1) fail('سطرُ «' + SEEN_DECL + '» ورد ' + hits + ' مرّة في runner_tail.js (المتوقَّع مرّة)');
const code =
  'await (async () => {\n' +
  fs.readFileSync(path.join(tools, 'gate.js'), 'utf8') +
  '\n' +
  tail.replace(SEEN_DECL, 'const SEEN = ' + JSON.stringify(seen) + ';') +
  '\n})()\n';
if (code.includes(SEEN_DECL)) fail('بقي التعريفُ الحرفيّ بعد الحقن');

// ٤) فحصُ الصياغة داخل دالّةٍ غير متزامنة (المشغِّلُ يبدأ بـ await على المستوى الأعلى).
try {
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  new AsyncFunction(code); // يُترجم ولا يُنفَّذ
} catch (e) {
  fail('خطأُ صياغة: ' + e.message);
}

fs.writeFileSync(out, code, 'utf8');
console.log('نجحت اختباراتُ البوّابة؛ التذاكرُ المفروزة: ' + seen.length + '؛ الأسطر: ' + code.split('\n').length);
console.log('المشغِّلُ الجاهز: ' + out);
