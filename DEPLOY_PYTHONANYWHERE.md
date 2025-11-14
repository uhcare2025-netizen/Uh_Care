# Deploy UH Care to PythonAnywhere

This document walks through deploying the UH Care Django project to PythonAnywhere.

Prerequisites
- A PythonAnywhere account (https://www.pythonanywhere.com/)
- Your project is pushed to GitHub (already pushed to: https://github.com/aaasaasthaassa-ux/UnitedHcare-.git)

Steps

1) Prepare your project locally

 - Ensure `requirements.txt` exists (it does in this repo). If you need to regenerate it locally:

```bash
pip freeze > requirements.txt
```

 - Set `DEBUG = False` on PythonAnywhere by using environment variables (do NOT hardcode secrets). The project already supports env vars:

   - On PythonAnywhere, set environment variable `DJANGO_DEBUG=False`
   - Set `DJANGO_ALLOWED_HOSTS` to your PythonAnywhere hostname, e.g. `yourusername.pythonanywhere.com`

 - Collect static files locally (optional) or run `collectstatic` on PythonAnywhere later:

```bash
python manage.py collectstatic --noinput
```

2) Upload code to PythonAnywhere

Recommended: clone from GitHub on PythonAnywhere

```bash
# on PythonAnywhere Bash console
git clone https://github.com/aaasaasthaassa-ux/UnitedHcare-.git
cd UnitedHcare-
```

3) Create and activate a virtualenv on PythonAnywhere

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

4) Configure the Web app on PythonAnywhere

- Go to the **Web** tab and add a new web app.
- Choose **Manual configuration** and the appropriate Python version (3.11 or 3.13).
- Edit the WSGI configuration file (link from the Web tab) and update paths:

```python
import sys, os
path = '/home/yourusername/UnitedHcare-'
if path not in sys.path:
    sys.path.append(path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `/home/yourusername/UnitedHcare-` and `yourusername` appropriately.

5) Set environment variables on PythonAnywhere

In the Web tab, under **Environment variables**, set:

- `DJANGO_DEBUG` = `False`
- `DJANGO_ALLOWED_HOSTS` = `yourusername.pythonanywhere.com`
- `DJANGO_SECRET_KEY` = set a secure secret key
- Any database or email env vars your project needs (e.g., `DATABASE_URL`, `EMAIL_HOST_USER`, etc.)

6) Point static files

In the Web tab, at **Static files** add a mapping:

- URL: `/static/`
- Directory: `/home/yourusername/UnitedHcare-/static`

Also ensure your `MEDIA` mapping if you use uploads:

- URL: `/media/`
- Directory: `/home/yourusername/UnitedHcare-/media`

7) Run migrations and collectstatic on PythonAnywhere

In a Bash console (inside your project and with venv activated):

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

8) Reload the web app from the Web tab

After reload, your site should be available at:

`https://yourusername.pythonanywhere.com`

Troubleshooting
- Check error logs on the Web tab if the app fails to start.
- Ensure your `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` are set correctly.
- For static problems, verify the Static files mapping and that `collectstatic` created files in the `staticfiles` or `static` directory.

If you'd like, I can:
- Add a short `pythonanywhere/` checklist file (done),
- Generate a recommended `production` environment file template (.env.example) with required env vars,
- Or help you run the required `collectstatic` and `migrate` commands on your local machine and prepare any additional instructions.
