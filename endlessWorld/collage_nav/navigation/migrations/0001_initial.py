# Generated by Django 5.2.1 on 2025-05-28 19:25

import django.contrib.auth.models
import django.contrib.auth.validators
import django.contrib.gis.db.models.fields
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('phone_number', models.CharField(max_length=17, unique=True, validators=[django.core.validators.RegexValidator(message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.", regex='^\\+?1?\\d{9,15}$')])),
                ('role', models.CharField(choices=[('student', 'Student'), ('staff', 'Staff'), ('visitor', 'Visitor')], default='student', max_length=10)),
                ('profile_picture', models.ImageField(blank=True, null=True, upload_to='profiles/')),
                ('is_verified', models.BooleanField(default=False)),
                ('verification_token', models.CharField(blank=True, max_length=6, null=True)),
                ('token_created_at', models.DateTimeField(blank=True, null=True)),
                ('dark_mode', models.BooleanField(default=False)),
                ('notifications_enabled', models.BooleanField(default=True)),
                ('location_sharing', models.BooleanField(default=True)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='customuser_set', related_query_name='customuser', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='customuser_set', related_query_name='customuser', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Geofence',
            fields=[
                ('geofence_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('boundary', django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ('radius', models.FloatField(default=100)),
                ('trigger_type', models.CharField(choices=[('entry', 'Entry'), ('exit', 'Exit'), ('both', 'Both')], default='entry', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='GeofenceEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_inside', models.BooleanField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('geofence', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='navigation.geofence')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='Location',
            fields=[
                ('location_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('location_type', models.CharField(choices=[('building', 'Building'), ('classroom', 'Classroom'), ('office', 'Office'), ('library', 'Library'), ('cafeteria', 'Cafeteria'), ('parking', 'Parking'), ('entrance', 'Entrance'), ('facility', 'Facility'), ('landmark', 'Landmark')], max_length=20)),
                ('coordinates', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('floor_level', models.IntegerField(default=0)),
                ('is_accessible', models.BooleanField(default=True)),
                ('capacity', models.IntegerField(blank=True, null=True)),
                ('operating_hours', models.CharField(blank=True, max_length=100)),
                ('contact_info', models.CharField(blank=True, max_length=100)),
                ('image', models.ImageField(blank=True, null=True, upload_to='locations/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [models.Index(fields=['location_type'], name='navigation__locatio_5795a8_idx'), models.Index(fields=['name'], name='navigation__name_ec9f29_idx')],
            },
        ),
        migrations.AddField(
            model_name='geofence',
            name='location',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='navigation.location'),
        ),
        migrations.CreateModel(
            name='NavigationRoute',
            fields=[
                ('route_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('route_path', django.contrib.gis.db.models.fields.LineStringField(srid=4326)),
                ('distance', models.FloatField()),
                ('estimated_time', models.IntegerField()),
                ('difficulty_level', models.CharField(choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')], default='easy', max_length=10)),
                ('is_accessible', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('destination_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes_to', to='navigation.location')),
                ('source_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes_from', to='navigation.location')),
            ],
        ),
        migrations.CreateModel(
            name='Recommendation',
            fields=[
                ('recommendation_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.CharField(max_length=200)),
                ('score', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='navigation.location')),
                ('recommended_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recommended_for', to='navigation.location')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-score', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RouteRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transport_mode', models.CharField(default='walking', max_length=20)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('from_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='route_requests_from', to='navigation.location')),
                ('to_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='route_requests_to', to='navigation.location')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SMSAlert',
            fields=[
                ('alert_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('message', models.TextField()),
                ('alert_type', models.CharField(choices=[('verification', 'Verification'), ('password_reset', 'Password Reset'), ('geofence', 'Geofence Alert'), ('notification', 'General Notification')], max_length=20)),
                ('is_sent', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UserLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('location', django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('accuracy', models.FloatField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='UserSearch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('search_query', models.CharField(max_length=200)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('search_location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='navigation.location')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
    ]
