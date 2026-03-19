import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Button } from '@/components/ui/button.tsx';
import { Badge } from '@/components/ui/badge.tsx';
import { ArrowLeft, CheckCircle2, AlertCircle, Clock, Target } from 'lucide-react';

const complianceDetails = [
  {
    name: 'قانون حماية البيانات الشخصية (PDPPL)',
    status: 'جزئي',
    percentage: 65,
    color: '#f59e0b',
    description: 'قانون رقم (13) لسنة 2016 بشأن حماية خصوصية البيانات الشخصية',
    requirements: [
      {
        title: 'تشفير البيانات الحساسة',
        status: 'مكتمل جزئياً',
        details: 'تم تطبيق التشفير على بعض الحقول فقط',
        recommendations: [
          'تطبيق التشفير على جميع الحقول الحساسة (الصحية، السلوكية)',
          'استخدام FERNET_KEY قوي في بيئة الإنتاج',
          'توثيق استراتيجية التشفير',
        ],
        priority: 'عاجل',
        timeline: '2-3 أسابيع',
      },
      {
        title: 'إدارة الموافقات (Consent Management)',
        status: 'غير مكتمل',
        details: 'نموذج ConsentRecord موجود لكنه غير مستخدم',
        recommendations: [
          'تفعيل نظام جمع الموافقات من أولياء الأمور',
          'إنشاء واجهات لإدارة الموافقات',
          'توثيق أنواع الموافقات المطلوبة',
        ],
        priority: 'عاجل',
        timeline: '3-4 أسابيع',
      },
      {
        title: 'تقييم أثر حماية البيانات (DPIA)',
        status: 'غير مكتمل',
        details: 'لا يوجد تقييم رسمي لأثر حماية البيانات',
        recommendations: [
          'تعيين مسؤول حماية البيانات (DPO)',
          'إجراء DPIA شامل',
          'توثيق النتائج والتوصيات',
        ],
        priority: 'مهم',
        timeline: '4-6 أسابيع',
      },
      {
        title: 'آلية الإبلاغ عن الخروقات',
        status: 'غير مكتمل',
        details: 'لا توجد آلية واضحة للإبلاغ عن خروقات البيانات',
        recommendations: [
          'وضع خطة استجابة للحوادث',
          'إعداد قنوات إبلاغ داخلية وخارجية',
          'تدريب الموظفين على الإبلاغ',
        ],
        priority: 'مهم',
        timeline: '2-3 أسابيع',
      },
      {
        title: 'سياسات الخصوصية والشروط',
        status: 'غير مكتمل',
        details: 'لا توجد سياسات خصوصية وشروط استخدام واضحة',
        recommendations: [
          'صياغة سياسة خصوصية شاملة',
          'صياغة شروط الاستخدام',
          'نشر السياسات بشكل واضح',
        ],
        priority: 'مهم',
        timeline: '2-3 أسابيع',
      },
    ],
  },
  {
    name: 'لائحة السلوك المدرسي القطرية',
    status: 'كامل',
    percentage: 95,
    color: '#10b981',
    description: 'لائحة السلوك والانضباط الطلابي في المدارس القطرية',
    requirements: [
      {
        title: 'تسجيل المخالفات السلوكية',
        status: 'مكتمل',
        details: 'نموذج BehaviorInfraction يدعم تسجيل المخالفات',
        recommendations: [
          'الحفاظ على هذا النظام',
          'إضافة تقارير تفصيلية',
          'تحسين واجهة الإدخال',
        ],
        priority: 'اختياري',
        timeline: 'تحسينات دورية',
      },
      {
        title: 'نظام الإنذارات والعقوبات',
        status: 'مكتمل',
        details: 'نظام تدرجي للعقوبات مطبق',
        recommendations: [
          'إضافة نظام إنذار مبكر للسلوك',
          'تحسين التقارير للأهالي',
          'إضافة تحليلات السلوك',
        ],
        priority: 'مهم',
        timeline: '3-4 أسابيع',
      },
      {
        title: 'التقارير والإحصائيات',
        status: 'جيد',
        details: 'تقارير أساسية موجودة',
        recommendations: [
          'إضافة تقارير متقدمة',
          'تحليل الأنماط السلوكية',
          'تقارير مخصصة حسب الأدوار',
        ],
        priority: 'مهم',
        timeline: '2-3 أسابيع',
      },
    ],
  },
  {
    name: 'معايير أوزان التقييم (40/60)',
    status: 'كامل',
    percentage: 98,
    color: '#10b981',
    description: 'معايير وزن التقييم المستمر والنهائي (40% مستمر، 60% نهائي)',
    requirements: [
      {
        title: 'حساب الدرجات المستمرة',
        status: 'مكتمل',
        details: 'نظام حساب الدرجات المستمرة (40%) مطبق',
        recommendations: [
          'التحقق من صحة الحسابات',
          'إضافة تقارير تفصيلية',
          'توثيق الصيغ المستخدمة',
        ],
        priority: 'اختياري',
        timeline: 'تحسينات دورية',
      },
      {
        title: 'حساب الدرجات النهائية',
        status: 'مكتمل',
        details: 'نظام حساب الدرجات النهائية (60%) مطبق',
        recommendations: [
          'التحقق من صحة الحسابات',
          'إضافة معايير النجاح والرسوب',
          'تقارير مقارنة مع السنوات السابقة',
        ],
        priority: 'اختياري',
        timeline: 'تحسينات دورية',
      },
      {
        title: 'التقارير الأكاديمية',
        status: 'مكتمل',
        details: 'تقارير أكاديمية شاملة متاحة',
        recommendations: [
          'تحسين تنسيق التقارير',
          'إضافة رسوم بيانية',
          'تقارير مقارنة بين الطلاب',
        ],
        priority: 'مهم',
        timeline: '2-3 أسابيع',
      },
    ],
  },
  {
    name: 'الاستراتيجية الوطنية للتعليم 2024-2030',
    status: 'جيد',
    percentage: 80,
    color: '#3b82f6',
    description: 'الاستراتيجية الوطنية للتعليم وأهدافها التنموية',
    requirements: [
      {
        title: 'التحول الرقمي',
        status: 'جيد',
        details: 'المنصة توفر أساس قوي للتحول الرقمي',
        recommendations: [
          'توسيع الميزات الرقمية',
          'تطبيق التعليم عن بعد',
          'دعم التعليم الهجين',
        ],
        priority: 'مهم',
        timeline: '4-6 أسابيع',
      },
      {
        title: 'الذكاء الاصطناعي والتحليلات',
        status: 'غير مكتمل',
        details: 'لا توجد ميزات AI متقدمة',
        recommendations: [
          'تطوير نموذج ML للتنبؤ بالأداء',
          'نظام توصيات مخصص',
          'تحليل البيانات المتقدم',
        ],
        priority: 'مهم',
        timeline: '3-6 أشهر',
      },
      {
        title: 'جودة التعليم والمراقبة',
        status: 'جيد',
        details: 'نظام مراقبة الجودة موجود',
        recommendations: [
          'تحسين مؤشرات الجودة',
          'إضافة معايير دولية',
          'تقارير مقارنة مع المدارس الأخرى',
        ],
        priority: 'مهم',
        timeline: '3-4 أسابيع',
      },
      {
        title: 'الشمول والعدالة',
        status: 'جيد',
        details: 'النظام يدعم جميع الطلاب',
        recommendations: [
          'تحسين إمكانية الوصول (Accessibility)',
          'دعم الطلاب ذوي الاحتياجات الخاصة',
          'توفير واجهات متعددة اللغات',
        ],
        priority: 'مهم',
        timeline: '4-6 أسابيع',
      },
    ],
  },
];

export default function ComplianceDetail() {
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
              <h1 className="text-3xl font-bold text-slate-900">الامتثال القانوني والتعليمي</h1>
              <p className="text-slate-600 mt-1">تقييم الامتثال للقوانين والسياسات القطرية مع التوصيات</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-8 space-y-8">
        {complianceDetails.map((compliance, idx) => (
          <div key={idx} className="space-y-4">
            {/* Compliance Header */}
            <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div className="flex-1">
                    <h2 className="text-2xl font-bold text-slate-900">{compliance.name}</h2>
                    <p className="text-slate-600 mt-1">{compliance.description}</p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Badge
                      className={
                        compliance.status === 'كامل'
                          ? 'bg-green-500 text-white'
                          : compliance.status === 'جيد'
                            ? 'bg-blue-500 text-white'
                            : 'bg-amber-500 text-white'
                      }
                    >
                      {compliance.status}
                    </Badge>
                    <span className="text-sm font-semibold text-slate-600">{compliance.percentage}% متوافق</span>
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-slate-200 rounded-full h-3">
                  <div
                    className="h-3 rounded-full transition-all duration-500"
                    style={{ width: `${compliance.percentage}%`, backgroundColor: compliance.color }}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Requirements */}
            <div className="grid grid-cols-1 gap-4">
              {compliance.requirements.map((req, i) => (
                <Card key={i} className="border-0 shadow-lg bg-white/80 backdrop-blur-sm hover:shadow-xl transition-shadow">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <CardTitle className="text-lg">{req.title}</CardTitle>
                        <CardDescription className="mt-2">{req.details}</CardDescription>
                      </div>
                      <div className="flex flex-col gap-2">
                        <Badge
                          variant={
                            req.status === 'مكتمل'
                              ? 'default'
                              : req.status === 'جيد'
                                ? 'secondary'
                                : 'outline'
                          }
                        >
                          {req.status}
                        </Badge>
                        {req.priority && (
                          <Badge
                            className={
                              req.priority === 'عاجل'
                                ? 'bg-red-500 text-white'
                                : req.priority === 'مهم'
                                  ? 'bg-orange-500 text-white'
                                  : 'bg-blue-500 text-white'
                            }
                          >
                            {req.priority}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-slate-900 mb-2">التوصيات</h4>
                      <ul className="space-y-2">
                        {req.recommendations.map((rec, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                            <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                            <span>{rec}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {req.timeline && (
                      <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <Clock className="w-4 h-4" />
                          الجدول الزمني: {req.timeline}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))}

        {/* Summary */}
        <Card className="border-0 shadow-lg bg-gradient-to-r from-blue-50 to-indigo-50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="w-5 h-5" />
              ملخص الامتثال
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-white/60 border border-blue-200">
                <h4 className="font-semibold text-blue-900 mb-2">النقاط الإيجابية</h4>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>✓ امتثال عالي للسياسات التعليمية</li>
                  <li>✓ نظام قوي لإدارة السلوك والتقييمات</li>
                  <li>✓ دعم أساسي للمتطلبات القانونية</li>
                </ul>
              </div>
              <div className="p-4 rounded-lg bg-white/60 border border-amber-200">
                <h4 className="font-semibold text-amber-900 mb-2">مجالات التحسين العاجلة</h4>
                <ul className="text-sm text-amber-800 space-y-1">
                  <li>⚠ تطبيق التشفير الشامل (PDPPL)</li>
                  <li>⚠ تفعيل نظام إدارة الموافقات</li>
                  <li>⚠ إجراء DPIA والإبلاغ عن الخروقات</li>
                </ul>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/60 border border-slate-200">
              <h4 className="font-semibold text-slate-900 mb-2">الخطوات التالية الموصى بها</h4>
              <ol className="text-sm text-slate-700 space-y-2">
                <li><strong>1. الأسبوع الأول:</strong> تطبيق التشفير على جميع الحقول الحساسة</li>
                <li><strong>2. الأسبوع الثاني:</strong> تفعيل نظام إدارة الموافقات</li>
                <li><strong>3. الأسبوع الثالث:</strong> صياغة سياسات الخصوصية والشروط</li>
                <li><strong>4. الشهر الثاني:</strong> إجراء DPIA وإعداد خطة الاستجابة للحوادث</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/50 bg-white/50 backdrop-blur-sm mt-12">
        <div className="container py-8 text-center text-slate-600">
          <p>تقييم الامتثال القانوني والتعليمي | جميع الحقوق محفوظة © 2026</p>
        </div>
      </footer>
    </div>
  );
}
