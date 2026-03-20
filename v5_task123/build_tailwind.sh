#!/bin/bash
# build_tailwind.sh — SchoolOS v5
# شغّله مرة واحدة لتصريف Tailwind وحذف CDN
# المتطلب: Node.js >= 16

echo "🔧 تثبيت Tailwind CSS..."
npm install -D tailwindcss@3

echo "⚙️  بناء tailwind.min.css..."
npx tailwindcss \
  -c tailwind.config.js \
  -i static/css/tailwind_input.css \
  -o static/css/tailwind.min.css \
  --minify

echo "✅ الحجم: $(du -sh static/css/tailwind.min.css)"
echo ""
echo "📝 الخطوة التالية: في templates/base/base.html"
echo "   احذف: <script src=\"https://cdn.tailwindcss.com\"></script>"
echo "   أضف:  <link rel=\"stylesheet\" href=\"{% static 'css/tailwind.min.css' %}\">"
