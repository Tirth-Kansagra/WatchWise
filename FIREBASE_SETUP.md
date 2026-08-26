# Firebase Google Sign-In Setup

The current landing page supports WatchWise email/password accounts immediately. Firebase enables the Google provider, while Streamlit's native OIDC flow uses a Google OAuth Web Client to open the account chooser and securely return the verified identity.

## Firebase Console

1. Create or select a Firebase project at https://console.firebase.google.com/.
2. Open **Authentication** -> **Sign-in method**.
3. Enable **Google** and choose a support email.
4. In **Project settings** -> **General**, create a Web app and copy its Firebase configuration.
5. Add the local app domain under **Authentication** -> **Settings** -> **Authorized domains**. For local development this is usually `localhost`.

## Google OAuth client for Streamlit

1. Open **Google Cloud Console** -> **APIs & Services** -> **Credentials**.
2. Create an **OAuth client ID** with application type **Web application**.
3. Add this authorized redirect URI for local development:

```text
http://localhost:8502/oauth2callback/google
```

4. Copy the client ID and client secret. The secret is different from the Firebase web API key and must remain private.

## Streamlit configuration

Create `.streamlit/secrets.toml` locally and never commit it:

```toml
[firebase]
api_key = "your-web-api-key"
auth_domain = "your-project.firebaseapp.com"
project_id = "your-project-id"
storage_bucket = "your-project.firebasestorage.app"
messaging_sender_id = "your-sender-id"
app_id = "your-web-app-id"
```

Add the OAuth settings to the same file:

```toml
[auth]
redirect_uri = "http://localhost:8502/oauth2callback/google"
cookie_secret = "generate-a-long-random-secret"

[auth.google]
client_id = "your-google-oauth-client-id.apps.googleusercontent.com"
client_secret = "your-google-oauth-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Generate `cookie_secret` locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

For deployment, add the same values in the hosting provider's Streamlit secrets manager.

## Important integration note

Firebase Authentication is a browser-side OAuth flow. A production Google login needs a small browser component or a separate OAuth callback service to receive the Firebase ID token. The backend must verify that token server-side, then link the verified Firebase UID to the local `users` row. Do not put a Firebase service-account private key in the browser or repository.

The local database links Google users using `auth_provider` + `provider_user_id`, while ratings continue to use the local user ID and TMDB movie ID.
