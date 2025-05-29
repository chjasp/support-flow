# Google OAuth Setup Instructions

The application requires Google OAuth credentials to enable user authentication. Follow these steps to set up Google OAuth:

## 1. Go to Google Cloud Console
Visit: https://console.cloud.google.com/

## 2. Create or Select a Project
- Create a new project or select an existing one
- Make note of your project ID

## 3. Enable Required APIs
- In the left sidebar, go to "APIs & Services" > "Library"
- Search for and enable: "Google+ API" or "Google Identity"

## 4. Create OAuth 2.0 Credentials
- Go to "APIs & Services" > "Credentials"
- Click "Create Credentials" > "OAuth 2.0 Client IDs"
- Choose "Web application" as the application type
- Give it a name (e.g., "Support Flow Frontend")

## 5. Configure Authorized URLs
Add these URLs to your OAuth client:

**Authorized JavaScript origins:**
```
http://localhost:3000
```

**Authorized redirect URIs:**
```
http://localhost:3000/api/auth/callback/google
```

## 6. Get Your Credentials
After creating the OAuth client, you'll get:
- Client ID (looks like: `123456789-abc...xyz.apps.googleusercontent.com`)
- Client Secret (looks like: `GOCSPX-...`)

## 7. Update Environment Variables
Edit the `.env.local` file in the `01-frontend` directory:

```env
GOOGLE_CLIENT_ID=your-actual-client-id-here
GOOGLE_CLIENT_SECRET=your-actual-client-secret-here
```

## 8. Restart the Development Server
After updating the environment variables:
```bash
cd 01-frontend
npm run dev
```

## Production Setup
For production deployment, make sure to:
1. Update the authorized origins and redirect URIs with your production domain
2. Use environment variables or secure secret management
3. Generate a strong `NEXTAUTH_SECRET`

## Troubleshooting
- Make sure the redirect URI exactly matches what's configured in Google Cloud Console
- Ensure the client ID and secret are correct
- Check that the Google+ API is enabled
- Verify the project has the OAuth consent screen configured 