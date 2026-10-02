from django.db import migrations


def renumber(apps, schema_editor):
    """Replace the 10, 20, 30… spacing with plain 1, 2, 3… within each category."""
    Skill = apps.get_model('credentialing', 'Skill')
    SkillCategory = apps.get_model('credentialing', 'SkillCategory')
    for cat in SkillCategory.objects.all():
        for i, skill in enumerate(cat.skills.order_by('order', 'name'), start=1):
            if skill.order != i:
                skill.order = i
                skill.save(update_fields=['order'])


class Migration(migrations.Migration):

    dependencies = [
        ('credentialing', '0002_physicist_location'),
    ]

    operations = [
        migrations.RunPython(renumber, migrations.RunPython.noop),
    ]
