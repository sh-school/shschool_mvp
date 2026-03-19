import { useState } from 'react';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.tsx';
import { Badge } from '@/components/ui/badge.tsx';
import { CheckCircle2, AlertCircle, TrendingUp, Shield, Code2, Users, Zap, Lock, Calendar } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import ArchitectureFlowchart from '@/components/ArchitectureFlowchart.tsx';
import DataFlowDiagram from '@/components/DataFlowDiagram.tsx';

const swotData = {
  strengths: [
    { title: 'معيارية الهيكلية', description: 'تقسيم منظم إلى Django Apps مع فصل واضح للمسؤوليات' },
    { title: 'Service Layer قوي', description: 'فصل منطق الأعمال عن الـ Views' },
    { title: 'قاعدة بيانات متقدمة', description: 'PostgreSQL مع دعم Multi-tenancy' },
    { title: 'API محترف', description: 'Django REST Framework مع هيكلية منظمة' },
  ],
  weaknesses: [
    { title: 'استعلامات قاعدة البيانات', description: 'قد تحتاج تحسين (N+1 problem)' },
    { title: 'التخزين المؤقت محدود', description: 'استخدام Redis محصور على الجلسات فقط' },
    { title: 'عدم وجود مهام غير متزامنة', description: 'لا توجد Celery للمهام الطويلة' },
    { title: 'توثيق API ناقص', description: 'عدم وجود Swagger/OpenAPI UI' },
  ],
  opportunities: [
    { title: 'الذكاء الاصطناعي', description: 'نظام إنذار مبكر للأداء والسلوك' },
    { title: 'التحليلات المتقدمة', description: 'لوحات تحكم تفاعلية' },
    { title: 'التوسع الجغرافي', description: '+300 مدرسة حكومية قطرية' },
    { title: 'ميزات جديدة', description: 'إدارة الموارد البشرية والأصول' },
  ],
  threats: [
    { title: 'المتطلبات القانونية', description: 'الامتثال الكامل لـ PDPPL' },
    { title: 'المنافسة', description: 'منصات تعليمية أخرى قد تقدم ميزات مشابهة' },
    { title: 'الأمان', description: 'تهديدات الأمن السيبراني' },
    { title: 'الأداء', description: 'زيادة عدد المستخدمين قد تؤثر على الأداء' },
  ],
};

const performanceData = [
  { name: 'الاستعلامات', value: 70, category: 'متوسط' },
  { name: 'التخزين المؤقت', value: 45, category: 'ضعيف' },
  { name: 'الأمان', value: 85, category: 'قوي' },
  { name: 'التوثيق', value: 50, category: 'متوسط' },
  { name: 'الاختبارات', value: 60, category: 'متوسط' },
  { name: 'معالجة الأخطاء', value: 60, category: 'متوسط' },
  { name: 'تحديد معدل الطلبات', value: 30, category: 'ضعيف' },
];

export default function Home() {
  const [activeTab, setActiveTab] = useState('overview');
  const [, navigate] = useLocation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Header */}
      <header className="border-b border-slate-200/50 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold text-slate-900">SHSchool Platform Analysis</h1>
              <p className="text-slate-600 mt-2">تحليل شامل واستراتيجي لمنصة إدارة المدارس</p>
            </div>
            <Badge className="bg-green-500 text-white px-4 py-2 text-base">تحليل شامل 2026</Badge>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-5 bg-white/50 backdrop-blur-sm border border-slate-200/50">
            <TabsTrigger value="overview">نظرة عامة</TabsTrigger>
            <TabsTrigger value="swot">تحليل SWOT</TabsTrigger>
            <TabsTrigger value="compliance">الامتثال</TabsTrigger>
            <TabsTrigger value="security">الأمان</TabsTrigger>
            <TabsTrigger value="architecture">الهيكلية</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6 mt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div
                onClick={() => navigate('/swot')}
                className="p-4 rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 border border-purple-200 cursor-pointer hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Users className="w-5 h-5 text-purple-600" />
                  <span className="font-semibold text-purple-900">تحليل SWOT</span>
                </div>
                <p className="text-sm text-purple-700">عرض التفاصيل الكاملة</p>
              </div>
              <div
                onClick={() => navigate('/compliance')}
                className="p-4 rounded-lg bg-gradient-to-br from-green-50 to-green-100 border border-green-200 cursor-pointer hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                  <span className="font-semibold text-green-900">الامتثال</span>
                </div>
                <p className="text-sm text-green-700">عرض التفاصيل الكاملة</p>
              </div>
              <div
                onClick={() => navigate('/security')}
                className="p-4 rounded-lg bg-gradient-to-br from-red-50 to-red-100 border border-red-200 cursor-pointer hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-5 h-5 text-red-600" />
                  <span className="font-semibold text-red-900">الأمان</span>
                </div>
                <p className="text-sm text-red-700">عرض التفاصيل الكاملة</p>
              </div>
              <div
                onClick={() => navigate('/roadmap')}
                className="p-4 rounded-lg bg-gradient-to-br from-indigo-50 to-indigo-100 border border-indigo-200 cursor-pointer hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="w-5 h-5 text-indigo-600" />
                  <span className="font-semibold text-indigo-900">خارطة الطريق</span>
                </div>
                <p className="text-sm text-indigo-700">عرض الجدول الزمني</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { icon: Code2, label: 'التقنيات المستخدمة', value: '8+', color: 'from-blue-500 to-blue-600' },
                { icon: Users, label: 'التطبيقات', value: '6', color: 'from-purple-500 to-purple-600' },
                { icon: Shield, label: 'مستوى الأمان', value: 'عالي', color: 'from-green-500 to-green-600' },
                { icon: Zap, label: 'الأداء', value: 'جيد', color: 'from-orange-500 to-orange-600' },
              ].map((stat, i) => (
                <Card key={i} className="border-0 shadow-lg bg-white/80 backdrop-blur-sm hover:shadow-xl transition-shadow">
                  <CardContent className="pt-6">
                    <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${stat.color} flex items-center justify-center text-white mb-4`}>
                      <stat.icon className="w-6 h-6" />
                    </div>
                    <h3 className="font-semibold text-slate-900">{stat.label}</h3>
                    <p className="text-2xl font-bold text-slate-600 mt-2">{stat.value}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
              <CardHeader>
                <CardTitle>الملخص التنفيذي</CardTitle>
                <CardDescription>نقاط رئيسية عن حالة المنصة</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-lg bg-green-50 border border-green-200">
                    <h4 className="font-semibold text-green-900 mb-2 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" />
                      نقاط القوة الرئيسية
                    </h4>
                    <ul className="text-sm text-green-800 space-y-1">
                      <li>✓ هيكلية معيارية وقابلة للتوسع</li>
                      <li>✓ نظام أمان قوي ومتعدد الطبقات</li>
                      <li>✓ قاعدة بيانات متقدمة وموثوقة</li>
                    </ul>
                  </div>
                  <div className="p-4 rounded-lg bg-amber-50 border border-amber-200">
                    <h4 className="font-semibold text-amber-900 mb-2 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      مجالات التحسين الأساسية
                    </h4>
                    <ul className="text-sm text-amber-800 space-y-1">
                      <li>⚠ تحسين استعلامات قاعدة البيانات</li>
                      <li>⚠ توسيع استخدام التخزين المؤقت</li>
                      <li>⚠ تطبيق التشفير الشامل</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* SWOT Tab */}
          <TabsContent value="swot" className="space-y-6 mt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { title: 'نقاط القوة', icon: CheckCircle2, color: 'green', data: swotData.strengths },
                { title: 'نقاط الضعف', icon: AlertCircle, color: 'amber', data: swotData.weaknesses },
                { title: 'الفرص', icon: TrendingUp, color: 'blue', data: swotData.opportunities },
                { title: 'التهديدات', icon: AlertCircle, color: 'red', data: swotData.threats },
              ].map((section, i) => {
                const Icon = section.icon;
                return (
                  <Card key={i} className="border-0 shadow-lg bg-white/80 backdrop-blur-sm hover:shadow-xl transition-shadow">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Icon className={`w-5 h-5 text-${section.color}-600`} />
                        {section.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-2">
                        {section.data.map((item, idx) => (
                          <li key={idx} className="text-sm text-slate-700">
                            <strong>{item.title}:</strong> {item.description}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
              <CardHeader>
                <CardTitle>ملخص التحليل</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-slate-700 mb-4">
                  المنصة لديها أساس تقني قوي جداً مع هيكلية معيارية وأمان متقدم. المجالات الرئيسية للتحسين تركز على الأداء والامتثال القانوني والميزات المتقدمة.
                </p>
                <button
                  onClick={() => navigate('/swot')}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  عرض التحليل التفصيلي
                </button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Compliance Tab */}
          <TabsContent value="compliance" className="space-y-6 mt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { name: 'قانون حماية البيانات', percentage: 65, color: '#f59e0b' },
                { name: 'السلوك المدرسي', percentage: 95, color: '#10b981' },
                { name: 'أوزان التقييم', percentage: 98, color: '#10b981' },
                { name: 'الاستراتيجية الوطنية', percentage: 80, color: '#3b82f6' },
              ].map((item, i) => (
                <Card key={i} className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold text-slate-900">{item.name}</h3>
                      <Badge className="text-white" style={{ backgroundColor: item.color }}>
                        {item.percentage}%
                      </Badge>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all duration-500"
                        style={{ width: `${item.percentage}%`, backgroundColor: item.color }}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <button
              onClick={() => navigate('/compliance')}
              className="w-full px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-semibold"
            >
              عرض تقييم الامتثال التفصيلي
            </button>
          </TabsContent>

          {/* Security Tab */}
          <TabsContent value="security" className="space-y-6 mt-6">
            <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
              <CardHeader>
                <CardTitle>تقييم الأمان</CardTitle>
                <CardDescription>تقييم شامل لآليات الأمان في المنصة</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { title: 'المصادقة والتفويض', status: 'قوي', color: 'green' },
                    { title: 'تشفير البيانات', status: 'جزئي', color: 'amber' },
                    { title: 'حماية التطبيق', status: 'متوسط', color: 'amber' },
                    { title: 'الأمان على مستوى البنية', status: 'جيد', color: 'blue' },
                  ].map((item, i) => (
                    <div key={i} className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                      <h4 className="font-semibold text-slate-900 mb-2">{item.title}</h4>
                      <Badge className={`bg-${item.color}-500 text-white`}>{item.status}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <button
              onClick={() => navigate('/security')}
              className="w-full px-4 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-semibold"
            >
              عرض تقييم الأمان التفصيلي
            </button>
          </TabsContent>

          {/* Architecture Tab */}
          <TabsContent value="architecture" className="space-y-6 mt-6">
            <ArchitectureFlowchart />
            <DataFlowDiagram />
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/50 bg-white/50 backdrop-blur-sm mt-12">
        <div className="container py-8 text-center text-slate-600">
          <p>تحليل منصة SHSchool الشامل | جميع الحقوق محفوظة © 2026</p>
        </div>
      </footer>
    </div>
  );
}
