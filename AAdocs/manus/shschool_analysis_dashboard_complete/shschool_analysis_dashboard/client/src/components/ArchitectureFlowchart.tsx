import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Database, Server, Globe, Lock, Users, Zap } from 'lucide-react';

export default function ArchitectureFlowchart() {
  return (
    <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>هيكلية المنصة التقنية</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-8">
          {/* Layer 1: Frontend */}
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-600 uppercase tracking-wide">الطبقة الأمامية (Frontend)</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                { icon: Globe, label: 'Django Templates', desc: 'واجهات ديناميكية' },
                { icon: Zap, label: 'HTMX', desc: 'تفاعلية بدون صفحة كاملة' },
                { icon: Users, label: 'JavaScript', desc: 'تفاعلات متقدمة' },
              ].map((item, i) => (
                <div key={i} className="p-3 rounded-lg bg-gradient-to-br from-blue-50 to-blue-100 border border-blue-200">
                  <div className="flex items-center gap-2 mb-2">
                    <item.icon className="w-4 h-4 text-blue-600" />
                    <span className="font-semibold text-sm text-blue-900">{item.label}</span>
                  </div>
                  <p className="text-xs text-blue-700">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="w-1 h-8 bg-gradient-to-b from-blue-400 to-purple-400 rounded-full" />
          </div>

          {/* Layer 2: Backend */}
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-600 uppercase tracking-wide">طبقة المنطق (Backend)</div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {[
                { icon: Server, label: 'Django Views', desc: 'معالجة الطلبات' },
                { icon: Zap, label: 'Service Layer', desc: 'منطق الأعمال' },
                { icon: Lock, label: 'Middleware', desc: 'الصلاحيات والأمان' },
                { icon: Users, label: 'API (DRF)', desc: 'واجهات برمجية' },
              ].map((item, i) => (
                <div key={i} className="p-3 rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 border border-purple-200">
                  <div className="flex items-center gap-2 mb-2">
                    <item.icon className="w-4 h-4 text-purple-600" />
                    <span className="font-semibold text-sm text-purple-900">{item.label}</span>
                  </div>
                  <p className="text-xs text-purple-700">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <div className="w-1 h-8 bg-gradient-to-b from-purple-400 to-green-400 rounded-full" />
          </div>

          {/* Layer 3: Data */}
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-600 uppercase tracking-wide">طبقة البيانات (Data)</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                { icon: Database, label: 'PostgreSQL', desc: 'قاعدة البيانات الرئيسية' },
                { icon: Zap, label: 'Redis', desc: 'التخزين المؤقت والجلسات' },
                { icon: Lock, label: 'Encryption', desc: 'تشفير البيانات الحساسة' },
              ].map((item, i) => (
                <div key={i} className="p-3 rounded-lg bg-gradient-to-br from-green-50 to-green-100 border border-green-200">
                  <div className="flex items-center gap-2 mb-2">
                    <item.icon className="w-4 h-4 text-green-600" />
                    <span className="font-semibold text-sm text-green-900">{item.label}</span>
                  </div>
                  <p className="text-xs text-green-700">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Key Features */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-indigo-50 to-blue-50 border border-indigo-200">
            <h4 className="font-semibold text-indigo-900 mb-3">المميزات الرئيسية</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
              {[
                '✓ Multi-tenant',
                '✓ RBAC',
                '✓ 2FA',
                '✓ Encryption',
                '✓ API',
                '✓ Caching',
                '✓ Logging',
                '✓ Monitoring',
              ].map((feature, i) => (
                <div key={i} className="text-indigo-700">{feature}</div>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
