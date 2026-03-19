from rest_framework import serializers
from .models import Session, StudentAttendance


class SessionSerializer(serializers.ModelSerializer):
    class_group_name = serializers.CharField(source="class_group.__str__", read_only=True)
    subject_name     = serializers.CharField(source="subject.name_ar",     read_only=True)
    status_display   = serializers.CharField(source="get_status_display",  read_only=True)

    class Meta:
        model  = Session
        fields = ["id", "class_group_name", "subject_name", "date",
                  "start_time", "end_time", "status", "status_display"]


class AttendanceSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source="student.full_name",      read_only=True)
    status_display = serializers.CharField(source="get_status_display",     read_only=True)

    class Meta:
        model  = StudentAttendance
        fields = ["id", "student_name", "status", "status_display",
                  "excuse_type", "marked_at"]
