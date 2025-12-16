import os
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model

# Create your views here.


def create_test_users(request):
	"""Create three test users (admin, pm, employee) for quick testing on Render.

	If `TEST_USERS_SECRET` environment variable is set, the POST must include the same
	secret in the `secret` field. If not set, the endpoint is open (use with caution).
	"""
	User = get_user_model()
	created = []

	if request.method == 'POST':
		provided = request.POST.get('secret', '')
		required = os.environ.get('TEST_USERS_SECRET')
		if required and provided != required:
			messages.error(request, 'Invalid secret token.')
			return redirect('create_test_users')

		def _create(username, email, role, is_staff=False, is_superuser=False):
			user, created_flag = User.objects.get_or_create(
				username=username,
				defaults={
					'email': email,
					'role': role,
					'is_staff': is_staff,
					'is_superuser': is_superuser,
				}
			)
			if created_flag:
				user.set_password('password123')
				user.save()
				created.append(username)

		_create('admin', 'admin@example.com', 'admin', is_staff=True, is_superuser=True)
		_create('pm', 'pm@example.com', 'pm')
		_create('employee', 'employee@example.com', 'developer')

		if created:
			messages.success(request, f"Created users: {', '.join(created)} (password: password123)")
		else:
			messages.info(request, 'No new users created; users may already exist.')

		return redirect('create_test_users')

	# GET
	context = {
		'test_users_secret_set': bool(os.environ.get('TEST_USERS_SECRET'))
	}
	return render(request, 'create_test_users.html', context)
