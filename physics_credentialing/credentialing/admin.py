from django.contrib import admin

from .models import Credential, Physicist, Skill, SkillCategory, UserProfile


@admin.register(Physicist)
class PhysicistAdmin(admin.ModelAdmin):
    list_display = ['last_name', 'first_name', 'email', 'title', 'is_active']
    list_filter = ['is_active']
    search_fields = ['first_name', 'last_name', 'email']


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']
    ordering = ['order']


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'subcategory', 'as_applicable', 'renewal_months', 'is_active']
    list_filter = ['category', 'as_applicable', 'is_active']
    search_fields = ['name', 'subcategory']


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ['physicist', 'skill', 'status', 'date_completed', 'verified_by']
    list_filter = ['status', 'skill__category']
    search_fields = ['physicist__last_name', 'skill__name']


admin.site.register(UserProfile)
