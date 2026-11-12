from django.contrib import admin

from .models import (CaseLog, ChecklistItem, ChecklistProgress, Credential, Physicist, Skill,
                     SkillCategory, TreatmentSystem, UserProfile)


@admin.register(Physicist)
class PhysicistAdmin(admin.ModelAdmin):
    list_display = ['last_name', 'first_name', 'email', 'title', 'is_active']
    list_filter = ['is_active']
    search_fields = ['first_name', 'last_name', 'email']


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']
    ordering = ['order']


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ['order', 'indent', 'text']


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    inlines = [ChecklistItemInline]
    list_display = ['name', 'category', 'subcategory', 'system_type', 'as_applicable', 'renewal_months', 'is_active']
    list_filter = ['category', 'system_type', 'as_applicable', 'is_active']
    search_fields = ['name', 'subcategory']


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ['physicist', 'skill', 'system', 'status', 'date_completed', 'verified_by']
    list_filter = ['status', 'skill__category', 'system']
    search_fields = ['physicist__last_name', 'skill__name']


@admin.register(TreatmentSystem)
class TreatmentSystemAdmin(admin.ModelAdmin):
    list_display = ['name', 'system_type', 'manufacturer', 'location', 'order', 'is_active']
    list_filter = ['system_type', 'is_active']
    search_fields = ['name', 'manufacturer', 'location']


admin.site.register(UserProfile)


@admin.register(CaseLog)
class CaseLogAdmin(admin.ModelAdmin):
    list_display = ['credential', 'date', 'case_type', 'role', 'performed_with']
    list_filter = ['role', 'credential__skill__category']
    search_fields = ['credential__physicist__last_name', 'credential__skill__name', 'case_type']


admin.site.register(ChecklistProgress)
