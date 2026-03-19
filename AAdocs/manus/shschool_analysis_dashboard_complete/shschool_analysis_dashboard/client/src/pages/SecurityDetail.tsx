import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Button } from '@/components/ui/button.tsx';
import { Badge } from '@/components/ui/badge.tsx';
import { ArrowLeft, Shield, AlertTriangle, CheckCircle2, Lock, Eye, Zap } from 'lucide-react';

const securityDetails = [
  {
    category: 'المصادقة والتفويض',
    icon: Lock,
    color: 'green',
    status: 'قوي',
    items: [
      {
        title: 'المصادقة الثنائية (2FA)',
        status: 'مكتمل',
        description: 'نظام MFA مطبق باستخدام TOTP',
        strengths: [
          'دعم Google Authenticator وتطبيقات مشابهة',
          'رموز احتياطية للطوارئ',
          'تسجيل محاولات الدخول',
        ],
        recommendations: [
          'إضافة خيارات MFA إضافية (SMS, Email)',
          'تحسين واجهة إعداد 2FA',
          'إضافة تنبيهات عند تفعيل 2FA',
        ],
      },
      {
        title: 'نظام الصلاحيات (RBAC)',
        status: 'قوي',
        description: 'نظام صلاحيات مخصص وقوي',
        strengths: [
          'أدوار متعددة (Admin, Teacher, Parent, Student)',
          'صلاحيات مفصلة لكل دور',
          'Middleware مخصص للتحقق من الصلاحيات',
        ],
        recommendations: [
          'إضافة صلاحيات ديناميكية',
          'توثيق شامل للأدوار والصلاحيات',
          'إضافة audit logging للتغييرات',
        ],
      },
      {
        title: 'إدارة الجلسات',
        status: 'جيد',
        description: 'استخدام Redis لتخزين الجلسات',
        strengths: [
          'جلسات آمنة مع timeout',
          'تخزين مركزي للجلسات',
          'دعم multiple devices',
        ],
        recommendations: [
          'تأمين خادم Redis بكلمة مرور قوية',
          'استخدام SSL/TLS للاتصال بـ Redis',
          'إضافة monitoring للجلسات',
        ],
      },
    ],
  },
  {
    category: 'تشفير البيانات',
    icon: Shield,
    color: 'amber',
    status: 'جزئي',
    items: [
      {
        title: 'تشفير البيانات أثناء النقل (TLS/SSL)',
        status: 'مكتمل',
        description: 'استخدام HTTPS في الإنتاج',
        strengths: [
          'شهادات SSL صالحة',
          'TLS 1.2+ مفعل',
          'HSTS مفعل',
        ],
        recommendations: [
          'استخدام TLS 1.3',
          'تحديث الشهادات تلقائياً',
          'إضافة Certificate Pinning',
        ],
      },
      {
        title: 'تشفير البيانات أثناء الراحة',
        status: 'جزئي',
        description: 'تشفير بعض الحقول الحساسة فقط',
        strengths: [
          'استخدام Fernet للتشفير',
          'تشفير البيانات الصحية والسلوكية',
        ],
        recommendations: [
          'تشفير جميع الحقول الحساسة',
          'استخدام مفاتيح تشفير قوية',
          'إدارة آمنة للمفاتيح',
          'تطبيق key rotation',
        ],
      },
      {
        title: 'تجزئة كلمات المرور (Password Hashing)',
        status: 'مكتمل',
        description: 'استخدام Django\'s password hashing',
        strengths: [
          'استخدام PBKDF2 أو bcrypt',
          'salt عشوائي لكل كلمة مرور',
          'تحديث الخوارزمية تلقائياً',
        ],
        recommendations: [
          'استخدام Argon2 بدلاً من PBKDF2',
          'زيادة عدد التكرارات',
          'إضافة معايير قوة كلمة المرور',
        ],
      },
    ],
  },
  {
    category: 'حماية التطبيق',
    icon: AlertTriangle,
    color: 'red',
    status: 'متوسط',
    items: [
      {
        title: 'حماية من هجمات CSRF',
        status: 'مكتمل',
        description: 'Django CSRF middleware مفعل',
        strengths: [
          'CSRF tokens على جميع النماذج',
          'التحقق من الـ Referer',
        ],
        recommendations: [
          'إضافة SameSite cookie attribute',
          'توثيق CSRF في الـ API',
          'اختبار دوري لـ CSRF',
        ],
      },
      {
        title: 'حماية من هجمات SQL Injection',
        status: 'مكتمل',
        description: 'استخدام ORM (Django ORM)',
        strengths: [
          'استخدام parameterized queries',
          'عدم استخدام raw SQL',
        ],
        recommendations: [
          'مراجعة أي استخدام لـ raw SQL',
          'إضافة input validation',
          'اختبار دوري للثغرات',
        ],
      },
      {
        title: 'حماية من هجمات XSS',
        status: 'جيد',
        description: 'Django templates توفر حماية أساسية',
        strengths: [
          'auto-escaping في templates',
          'حماية من XSS stored',
        ],
        recommendations: [
          'تطبيق CSP (Content Security Policy)',
          'استخدام django-csp',
          'اختبار دوري لـ XSS',
        ],
      },
      {
        title: 'حماية من هجمات Brute Force',
        status: 'جزئي',
        description: 'حماية أساسية موجودة',
        strengths: [
          'تسجيل محاولات الدخول الفاشلة',
        ],
        recommendations: [
          'تطبيق rate limiting',
          'قفل الحساب بعد محاولات فاشلة',
          'إرسال تنبيهات للمستخدم',
        ],
      },
    ],
  },
  {
    category: 'الأمان على مستوى البنية',
    icon: Eye,
    color: 'blue',
    status: 'جيد',
    items: [
      {
        title: 'تسجيل الأمان (Security Logging)',
        status: 'جيد',
        description: 'تسجيل الأحداث الأمنية',
        strengths: [
          'تسجيل محاولات الدخول',
          'تسجيل تغييرات البيانات',
          'تسجيل الأخطاء',
        ],
        recommendations: [
          'مركزية السجلات (Centralized Logging)',
          'تحليل السجلات تلقائياً',
          'الاحتفاظ بالسجلات طويلة الأمد',
          'إضافة monitoring والتنبيهات',
        ],
      },
      {
        title: 'مراقبة الأمان (Security Monitoring)',
        status: 'متوسط',
        description: 'مراقبة أساسية موجودة',
        strengths: [
          'تسجيل الأحداث غير العادية',
        ],
        recommendations: [
          'تطبيق SIEM (Security Information and Event Management)',
          'إضافة IDS (Intrusion Detection System)',
          'مراقبة 24/7',
          'فريق أمان مخصص',
        ],
      },
      {
        title: 'النسخ الاحتياطية والاسترجاع',
        status: 'غير معروف',
        description: 'لا توجد معلومات واضحة',
        strengths: [],
        recommendations: [
          'إعداد نسخ احتياطية منتظمة',
          'اختبار استرجاع النسخ الاحتياطية',
          'تشفير النسخ الاحتياطية',
          'تخزين النسخ في مكان آمن',
          'خطة استرجاع الكوارث (Disaster Recovery)',
        ],
      },
      {
        title: 'تحديثات الأمان',
        status: 'متوسط',
        description: 'تحديثات دورية للمكتبات',
        strengths: [
          'استخدام pip للإدارة',
        ],
        recommendations: [
          'تحديثات أمنية فورية',
          'اختبار التحديثات قبل النشر',
          'استخدام tools مثل Dependabot',
          'مراجعة دورية للمكتبات',
        ],
      },
    ],
  },
];

export default function SecurityDetail() {
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
              <h1 className="text-3xl font-bold text-slate-900">تقييم الأمان التفصيلي</h1>
              <p className="text-slate-600 mt-1">تحليل شامل لآليات الأمان والتوصيات</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-8 space-y-8">
        {securityDetails.map((section, idx) => {
          const Icon = section.icon;
          const statusColor =
            section.status === 'قوي'
              ? 'bg-green-500'
              : section.status === 'جيد'
                ? 'bg-blue-500'
                : section.status === 'متوسط'
                  ? 'bg-amber-500'
                  : 'bg-red-500';

          return (
            <div key={idx} className="space-y-4">
              <div className="flex items-center gap-3 mb-6">
                <div className={`p-3 rounded-lg bg-gradient-to-br from-${section.color}-50 to-${section.color}-100`}>
                  <Icon className={`w-6 h-6 text-${section.color}-600`} />
                </div>
                <div className="flex-1">
                  <h2 className="text-2xl font-bold text-slate-900">{section.category}</h2>
                </div>
                <Badge className={statusColor}>{section.status}</Badge>
              </div>

              <div className="grid grid-cols-1 gap-4">
                {section.items.map((item, i) => (
                  <Card key={i} className="border-0 shadow-lg bg-white/80 backdrop-blur-sm hover:shadow-xl transition-shadow">
                    <CardHeader>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <CardTitle className="text-lg">{item.title}</CardTitle>
                          <CardDescription className="mt-2">{item.description}</CardDescription>
                        </div>
                        <Badge
                          variant={
                            item.status === 'مكتمل'
                              ? 'default'
                              : item.status === 'جيد'
                                ? 'secondary'
                                : 'outline'
                          }
                        >
                          {item.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {item.strengths && item.strengths.length > 0 && (
                        <div>
                          <h4 className="font-semibold text-green-900 mb-2 flex items-center gap-2">
                            <CheckCircle2 className="w-4 h-4" />
                            نقاط القوة
                          </h4>
                          <ul className="space-y-1">
                            {item.strengths.map((strength, i) => (
                              <li key={i} className="text-sm text-slate-700 flex items-start gap-2">
                                <span className="text-green-600 font-bold">✓</span>
                                <span>{strength}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div>
                        <h4 className="font-semibold text-slate-900 mb-2 flex items-center gap-2">
                          <Zap className="w-4 h-4" />
                          التوصيات
                        </h4>
                        <ul className="space-y-2">
                          {item.recommendations.map((rec, i) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                              <span className="text-blue-600 font-bold mt-0.5">→</span>
                              <span>{rec}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          );
        })}

        {/* Security Roadmap */}
        <Card className="border-0 shadow-lg bg-gradient-to-r from-red-50 to-orange-50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              خارطة طريق الأمان
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="p-4 rounded-lg bg-white/60 border border-red-200">
                <h4 className="font-semibold text-red-900 mb-2">المرحلة 1: الأسبوع الأول (عاجل)</h4>
                <ul className="text-sm text-red-800 space-y-1">
                  <li>✓ تطبيق التشفير على جميع الحقول الحساسة</li>
                  <li>✓ تأمين خادم Redis بكلمة مرور قوية</li>
                  <li>✓ إضافة SameSite cookie attribute</li>
                </ul>
              </div>

              <div className="p-4 rounded-lg bg-white/60 border border-orange-200">
                <h4 className="font-semibold text-orange-900 mb-2">المرحلة 2: الأسابيع 2-3 (مهم)</h4>
                <ul className="text-sm text-orange-800 space-y-1">
                  <li>✓ تطبيق rate limiting</li>
                  <li>✓ تطبيق CSP (Content Security Policy)</li>
                  <li>✓ إعداد مركزية السجلات (Centralized Logging)</li>
                </ul>
              </div>

              <div className="p-4 rounded-lg bg-white/60 border border-amber-200">
                <h4 className="font-semibold text-amber-900 mb-2">المرحلة 3: الشهر الثاني (مهم)</h4>
                <ul className="text-sm text-amber-800 space-y-1">
                  <li>✓ اختبارات اختراق شاملة</li>
                  <li>✓ إعداد خطة استرجاع الكوارث</li>
                  <li>✓ تطبيق SIEM</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/50 bg-white/50 backdrop-blur-sm mt-12">
        <div className="container py-8 text-center text-slate-600">
          <p>تقييم الأمان التفصيلي | جميع الحقوق محفوظة © 2026</p>
        </div>
      </footer>
    </div>
  );
}
