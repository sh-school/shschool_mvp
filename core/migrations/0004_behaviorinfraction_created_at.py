from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_parentstudentlink_id_alter_role_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='behaviorinfraction',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]
