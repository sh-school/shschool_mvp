import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card.tsx';
import { Users, BookOpen, BarChart3, Settings, Shield, Bell } from 'lucide-react';

export default function DataFlowDiagram() {
  return (
    <Card className="border-0 shadow-lg bg-white/80 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>تدفق البيانات والتطبيقات</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Core Module */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-red-50 to-rose-50 border border-red-200">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-5 h-5 text-red-600" />
              <h4 className="font-semibold text-red-900">Core (الأساس)</h4>
            </div>
            <p className="text-sm text-red-700 mb-2">إدارة المستخدمين والمدارس والصلاحيات</p>
            <div className="text-xs text-red-600">Models: User, School, Membership, Role, Permission</div>
          </div>

          {/* Operations Module */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-blue-50 to-cyan-50 border border-blue-200">
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="w-5 h-5 text-blue-600" />
              <h4 className="font-semibold text-blue-900">Operations (العمليات)</h4>
            </div>
            <p className="text-sm text-blue-700 mb-2">إدارة الجداول والحصص والمعلمين والحضور</p>
            <div className="text-xs text-blue-600">Models: Teacher, Class, Schedule, Attendance, Substitute</div>
          </div>

          {/* Assessments Module */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200">
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 className="w-5 h-5 text-purple-600" />
              <h4 className="font-semibold text-purple-900">Assessments (التقييمات)</h4>
            </div>
            <p className="text-sm text-purple-700 mb-2">إدارة الاختبارات والدرجات والتقارير الأكاديمية</p>
            <div className="text-xs text-purple-600">Models: Assessment, Grade, Report, StudentPerformance</div>
          </div>

          {/* Quality Module */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200">
            <div className="flex items-center gap-2 mb-3">
              <Settings className="w-5 h-5 text-green-600" />
              <h4 className="font-semibold text-green-900">Quality (الجودة)</h4>
            </div>
            <p className="text-sm text-green-700 mb-2">متابعة الجودة والتقييمات والمؤشرات</p>
            <div className="text-xs text-green-600">Models: QualityMetric, Observation, Indicator</div>
          </div>

          {/* Behavior Module */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-orange-50 to-amber-50 border border-orange-200">
            <div className="flex items-center gap-2 mb-3">
              <Bell className="w-5 h-5 text-orange-600" />
              <h4 className="font-semibold text-orange-900">Behavior (السلوك)</h4>
            </div>
            <p className="text-sm text-orange-700 mb-2">تسجيل الانضباط والسلوك والمخالفات</p>
            <div className="text-xs text-orange-600">Models: BehaviorInfraction, Discipline, StudentBehavior</div>
          </div>

          {/* Data Integration */}
          <div className="p-4 rounded-lg bg-gradient-to-r from-slate-100 to-slate-50 border border-slate-300">
            <h4 className="font-semibold text-slate-900 mb-3">تكامل البيانات</h4>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-slate-400" />
                <span className="text-slate-700">جميع التطبيقات تعتمد على Core لإدارة المستخدمين والصلاحيات</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-slate-400" />
                <span className="text-slate-700">Operations توفر البيانات الأساسية للتقييمات والسلوك</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-slate-400" />
                <span className="text-slate-700">جميع البيانات تُخزن في PostgreSQL مع تشفير للحقول الحساسة</span>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
