import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Button } from '@/components/ui/button.tsx';
import { Badge } from '@/components/ui/badge.tsx';
import { ArrowLeft, Calendar, Flag, CheckCircle2, AlertCircle, Zap } from 'lucide-react';

interface RoadmapItem {
  id: string;
  title: string;
  description: string;
  priority: 'عاجل' | 'مهم' | 'اختياري';
  category: string;
  startMonth: number;
  duration: number;
  status: 'مكتمل' | 'جاري' | 'مخطط' | 'معلق';
  owner: string;
  resources: string[];
}

const roadmapItems: RoadmapItem[] = [
  // الشهر الأول - الأسبوع الأول
  {
    id: 'r1',
    title: 'تطبيق التشفير الشامل للبيانات الحساسة',
    description: 'تشفير جميع الحقول الحساسة (الصحية، السلوكية) باستخدام Fernet',
    priority: 'عاجل',
    category: 'الأمان',
    startMonth: 0,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق الأمان',
    resources: ['مهندس أمان', 'مطور Backend'],
  },
  {
    id: 'r2',
    title: 'تأمين خادم Redis',
    description: 'إضافة كلمة مرور قوية واستخدام SSL/TLS',
    priority: 'عاجل',
    category: 'الأمان',
    startMonth: 0,
    duration: 1,
    status: 'مخطط',
    owner: 'فريق DevOps',
    resources: ['مهندس DevOps'],
  },
  {
    id: 'r3',
    title: 'إضافة SameSite Cookie Attribute',
    description: 'تحسين حماية CSRF',
    priority: 'عاجل',
    category: 'الأمان',
    startMonth: 0,
    duration: 1,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },

  // الشهر الأول - الأسبوع الثاني
  {
    id: 'r4',
    title: 'تفعيل نظام إدارة الموافقات',
    description: 'إنشاء واجهات لجمع الموافقات من أولياء الأمور',
    priority: 'عاجل',
    category: 'الامتثال',
    startMonth: 1,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق Frontend',
    resources: ['مطور Frontend', 'مطور Backend', 'مصمم UX'],
  },
  {
    id: 'r5',
    title: 'صياغة سياسات الخصوصية والشروط',
    description: 'إعداد سياسة خصوصية شاملة وشروط استخدام',
    priority: 'عاجل',
    category: 'الامتثال',
    startMonth: 1,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق القانون',
    resources: ['محامي', 'مستشار قانوني'],
  },

  // الشهر الأول - الأسبوع الثالث
  {
    id: 'r6',
    title: 'تطبيق Rate Limiting',
    description: 'حماية من هجمات Brute Force والطلبات المتكررة',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 2,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },
  {
    id: 'r7',
    title: 'تطبيق CSP (Content Security Policy)',
    description: 'حماية من هجمات XSS',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 2,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },

  // الشهر الثاني
  {
    id: 'r8',
    title: 'إجراء DPIA (تقييم أثر حماية البيانات)',
    description: 'تقييم شامل لأثر حماية البيانات',
    priority: 'مهم',
    category: 'الامتثال',
    startMonth: 4,
    duration: 4,
    status: 'مخطط',
    owner: 'مسؤول حماية البيانات',
    resources: ['DPO', 'محامي', 'مهندس أمان'],
  },
  {
    id: 'r9',
    title: 'إعداد خطة استرجاع الكوارث',
    description: 'نسخ احتياطية منتظمة واختبار الاسترجاع',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 4,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق DevOps',
    resources: ['مهندس DevOps', 'مهندس قاعدة بيانات'],
  },
  {
    id: 'r10',
    title: 'تحسين استعلامات قاعدة البيانات',
    description: 'إصلاح مشاكل N+1 وتطبيق select_related/prefetch_related',
    priority: 'مهم',
    category: 'الأداء',
    startMonth: 4,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend', 'مهندس قاعدة بيانات'],
  },

  // الشهر الثالث
  {
    id: 'r11',
    title: 'توثيق API (Swagger/OpenAPI)',
    description: 'إضافة توثيق شامل للـ API',
    priority: 'مهم',
    category: 'التطوير',
    startMonth: 6,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },
  {
    id: 'r12',
    title: 'إعداد مركزية السجلات (Centralized Logging)',
    description: 'تجميع ومراقبة السجلات من جميع الخوادم',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 6,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق DevOps',
    resources: ['مهندس DevOps'],
  },
  {
    id: 'r13',
    title: 'تطوير نموذج ML للتنبؤ بالأداء',
    description: 'نظام إنذار مبكر للأداء الأكاديمي',
    priority: 'مهم',
    category: 'الذكاء الاصطناعي',
    startMonth: 6,
    duration: 8,
    status: 'مخطط',
    owner: 'فريق Data Science',
    resources: ['Data Scientist', 'مهندس ML', 'مطور Backend'],
  },

  // الشهر الرابع والخامس
  {
    id: 'r14',
    title: 'اختبارات اختراق شاملة',
    description: 'Penetration Testing من قبل متخصصين',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 8,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق الأمان',
    resources: ['متخصص أمان سيبراني'],
  },
  {
    id: 'r15',
    title: 'تطبيق SIEM (Security Information and Event Management)',
    description: 'نظام مراقبة أمان متقدم',
    priority: 'مهم',
    category: 'الأمان',
    startMonth: 8,
    duration: 4,
    status: 'مخطط',
    owner: 'فريق الأمان',
    resources: ['متخصص أمان', 'مهندس DevOps'],
  },
  {
    id: 'r16',
    title: 'تحسين تجربة المستخدم والتصميم',
    description: 'إعادة تصميم الواجهة بناءً على feedback المستخدمين',
    priority: 'مهم',
    category: 'UX/UI',
    startMonth: 8,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق Frontend',
    resources: ['مصمم UX', 'مطور Frontend'],
  },

  // الشهر السادس والسابع
  {
    id: 'r17',
    title: 'توسيع استخدام التخزين المؤقت',
    description: 'تطبيق caching strategies متقدمة',
    priority: 'مهم',
    category: 'الأداء',
    startMonth: 10,
    duration: 2,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },
  {
    id: 'r18',
    title: 'تطبيق Celery للمهام غير المتزامنة',
    description: 'معالجة المهام الطويلة الأمد',
    priority: 'مهم',
    category: 'الأداء',
    startMonth: 10,
    duration: 3,
    status: 'مخطط',
    owner: 'فريق Backend',
    resources: ['مطور Backend'],
  },
  {
    id: 'r19',
    title: 'إضافة نظام توصيات مخصص',
    description: 'توصيات تعليمية مخصصة للمعلمين والطلاب',
    priority: 'مهم',
    category: 'الذكاء الاصطناعي',
    startMonth: 10,
    duration: 6,
    status: 'مخطط',
    owner: 'فريق Data Science',
    resources: ['Data Scientist', 'مطور Backend'],
  },
];

const monthLabels = [
  'الأسبوع 1',
  'الأسبوع 2',
  'الأسبوع 3',
  'الأسبوع 4',
  'الشهر 2',
  'الشهر 2',
  'الشهر 3',
  'الشهر 3',
  'الشهر 4-5',
  'الشهر 4-5',
  'الشهر 6-7',
  'الشهر 6-7',
];

const priorityColors = {
  عاجل: 'from-red-500 to-red-600',
  مهم: 'from-orange-500 to-orange-600',
  اختياري: 'from-blue-500 to-blue-600',
};

const categoryColors: Record<string, string> = {
  'الأمان': 'bg-red-100 text-red-800 border-red-300',
  'الامتثال': 'bg-green-100 text-green-800 border-green-300',
  'الأداء': 'bg-blue-100 text-blue-800 border-blue-300',
  'التطوير': 'bg-purple-100 text-purple-800 border-purple-300',
  'UX/UI': 'bg-pink-100 text-pink-800 border-pink-300',
  'الذكاء الاصطناعي': 'bg-indigo-100 text-indigo-800 border-indigo-300',
};

export default function Roadmap() {
  const [, navigate] = useLocation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Header */}
      <header className="border-b border-slate-200/50 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container py-6">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate('/')}
              className="hover:bg-slate-100"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold text-slate-900">خارطة الطريق الاستراتيجية</h1>
              <p className="text-slate-600 mt-1">خطة التنفيذ الشاملة لتحسين منصة SHSchool (6-12 شهر)</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-8 space-y-8">
        {/* Legend */}
        <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
          <CardHeader>
            <CardTitle>مفتاح الألوان والرموز</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-semibold text-slate-900 mb-3">الأولويات</h4>
                <div className="space-y-2">
                  {Object.entries(priorityColors).map(([priority, color]) => (
                    <div key={priority} className="flex items-center gap-3">
                      <div className={`w-4 h-4 rounded bg-gradient-to-r ${color}`} />
                      <span className="text-sm text-slate-700">{priority}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="font-semibold text-slate-900 mb-3">الفئات</h4>
                <div className="space-y-2">
                  {Object.entries(categoryColors).map(([category, colors]) => (
                    <div key={category} className="flex items-center gap-3">
                      <div className={`px-2 py-1 rounded text-xs font-semibold ${colors}`}>
                        {category}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Gantt Chart */}
        <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm overflow-hidden">
          <CardHeader>
            <CardTitle>مخطط جانت - الجدول الزمني للتنفيذ</CardTitle>
            <CardDescription>اسحب أفقياً لعرض الجدول الزمني الكامل</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto pb-4">
              <div className="min-w-max">
                {/* Timeline Header */}
                <div className="flex gap-0 mb-4">
                  <div className="w-64 flex-shrink-0 pr-4 border-r border-slate-200">
                    <div className="text-xs font-semibold text-slate-600 uppercase">المهمة</div>
                  </div>
                  <div className="flex gap-1">
                    {monthLabels.map((month, idx) => (
                      <div key={idx} className="w-16 flex-shrink-0 text-center">
                        <div className="text-xs font-semibold text-slate-600">{month}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Timeline Rows */}
                {roadmapItems.map((item) => (
                  <div key={item.id} className="flex gap-0 mb-3 items-center">
                    {/* Task Info */}
                    <div className="w-64 flex-shrink-0 pr-4 border-r border-slate-200">
                      <div className="space-y-1">
                        <h4 className="text-sm font-semibold text-slate-900">{item.title}</h4>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="outline"
                            className={`text-xs ${categoryColors[item.category]}`}
                          >
                            {item.category}
                          </Badge>
                          <Badge
                            className={`text-xs text-white bg-gradient-to-r ${
                              priorityColors[item.priority]
                            }`}
                          >
                            {item.priority}
                          </Badge>
                        </div>
                      </div>
                    </div>

                    {/* Gantt Bar */}
                    <div className="flex gap-1">
                      {monthLabels.map((_, idx) => {
                        const isInRange =
                          idx >= item.startMonth && idx < item.startMonth + item.duration;
                        const isStart = idx === item.startMonth;
                        const isEnd = idx === item.startMonth + item.duration - 1;

                        return (
                          <div key={idx} className="w-16 flex-shrink-0">
                            {isInRange && (
                              <div
                                className={`h-8 bg-gradient-to-r ${priorityColors[item.priority]} rounded-sm flex items-center justify-center text-white text-xs font-semibold transition-all hover:shadow-lg cursor-pointer`}
                                title={`${item.title} - ${item.duration} أسابيع`}
                              >
                                {isStart && isEnd && '✓'}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Detailed Timeline */}
        <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
          <CardHeader>
            <CardTitle>تفاصيل الجدول الزمني</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {roadmapItems.map((item) => (
              <div
                key={item.id}
                className="p-4 rounded-lg border border-slate-200 hover:border-blue-300 hover:shadow-md transition-all"
              >
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex-1">
                    <h4 className="font-semibold text-slate-900 mb-1">{item.title}</h4>
                    <p className="text-sm text-slate-600">{item.description}</p>
                  </div>
                  <div className="flex flex-col gap-2 items-end">
                    <Badge
                      className={`text-white bg-gradient-to-r ${priorityColors[item.priority]}`}
                    >
                      {item.priority}
                    </Badge>
                    <Badge variant="outline" className={categoryColors[item.category]}>
                      {item.category}
                    </Badge>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-slate-600">المالك:</span>
                    <p className="font-semibold text-slate-900">{item.owner}</p>
                  </div>
                  <div>
                    <span className="text-slate-600">المدة:</span>
                    <p className="font-semibold text-slate-900">{item.duration} أسابيع</p>
                  </div>
                  <div>
                    <span className="text-slate-600">البداية:</span>
                    <p className="font-semibold text-slate-900">{monthLabels[item.startMonth]}</p>
                  </div>
                  <div>
                    <span className="text-slate-600">الحالة:</span>
                    <p className="font-semibold text-slate-900">{item.status}</p>
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-slate-200">
                  <span className="text-sm text-slate-600">الموارد المطلوبة:</span>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {item.resources.map((resource, idx) => (
                      <Badge key={idx} variant="secondary" className="text-xs">
                        {resource}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Summary Statistics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="border-0 shadow-lg bg-gradient-to-br from-red-50 to-red-100">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-red-600 font-semibold">مهام عاجلة</p>
                  <p className="text-3xl font-bold text-red-900">
                    {roadmapItems.filter((i) => i.priority === 'عاجل').length}
                  </p>
                </div>
                <Flag className="w-8 h-8 text-red-600 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-lg bg-gradient-to-br from-orange-50 to-orange-100">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-orange-600 font-semibold">مهام مهمة</p>
                  <p className="text-3xl font-bold text-orange-900">
                    {roadmapItems.filter((i) => i.priority === 'مهم').length}
                  </p>
                </div>
                <AlertCircle className="w-8 h-8 text-orange-600 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-lg bg-gradient-to-br from-blue-50 to-blue-100">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-blue-600 font-semibold">إجمالي المهام</p>
                  <p className="text-3xl font-bold text-blue-900">{roadmapItems.length}</p>
                </div>
                <Zap className="w-8 h-8 text-blue-600 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-lg bg-gradient-to-br from-green-50 to-green-100">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-semibold">المدة الإجمالية</p>
                  <p className="text-3xl font-bold text-green-900">6-12 شهر</p>
                </div>
                <Calendar className="w-8 h-8 text-green-600 opacity-50" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Implementation Notes */}
        <Card className="border-0 shadow-lg bg-gradient-to-r from-indigo-50 to-purple-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5" />
              ملاحظات التنفيذ
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-700">
            <p>
              <strong>المرحلة الأولى (الأسابيع 1-4):</strong> التركيز على الأمان والامتثال
              القانوني الفوري لضمان حماية البيانات والامتثال لـ PDPPL.
            </p>
            <p>
              <strong>المرحلة الثانية (الشهر الثاني):</strong> تحسين الأداء والبنية التحتية
              مع إجراء تقييمات شاملة والتخطيط للمهام المستقبلية.
            </p>
            <p>
              <strong>المرحلة الثالثة (الشهر الثالث فما بعده):</strong> تطوير ميزات متقدمة
              مثل الذكاء الاصطناعي وتحسين تجربة المستخدم.
            </p>
            <p>
              <strong>الموارد المطلوبة:</strong> فريق متعدد التخصصات يضم مهندسي Backend و
              Frontend وأمان و DevOps ومتخصصي Data Science.
            </p>
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/50 bg-white/50 backdrop-blur-sm mt-12">
        <div className="container py-8 text-center text-slate-600">
          <p>خارطة الطريق الاستراتيجية | جميع الحقوق محفوظة © 2026</p>
        </div>
      </footer>
    </div>
  );
}
