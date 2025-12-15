# Authentication Documentation

## Overview

The Atria University Academic Management System uses session-based authentication with the LearnX API. Users must authenticate before accessing any module of the application.

## Authentication Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   User visits   │────▶│   Login Page    │────▶│   LearnX API    │
│      app        │     │  (Email/Pass)   │     │    /signin      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                              ┌───────────────────────────┘
                              ▼
                  ┌─────────────────────────┐
                  │   Status 200?           │
                  └─────────────────────────┘
                        │           │
                   Yes  │           │  No
                        ▼           ▼
              ┌─────────────┐  ┌─────────────┐
              │ Store Token │  │ Show Error  │
              │ in Cookie   │  │   Message   │
              │ Redirect to │  └─────────────┘
              │  Main App   │
              └─────────────┘
```

## API Endpoint

### Sign In

**Endpoint:** `POST https://learnx.atriauniversity.in/api/v1/auth/signin`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**Success Response (200):**
```json
{
  "token": "jwt_token_here",
  "user": {
    "id": "user_id",
    "email": "user@example.com",
    "name": "User Name"
  }
}
```

**Error Response (401/400):**
```json
{
  "message": "Invalid email or password"
}
```

## Session Management

### Browser Cookie Storage

The application uses **browser cookies** for session persistence via `streamlit-cookies-controller`.

**Cookie Details:**
| Setting | Value |
|---------|-------|
| Cookie Name | `au_auth_session` |
| Expiry | 7 days |
| Content | `email|token` |

### Session State Variables

| Variable | Type | Description |
|----------|------|-------------|
| `authenticated` | `bool` | Whether user is logged in |
| `auth_token` | `str` | JWT token from API |
| `user_email` | `str` | Logged-in user's email |

### How Cookie Persistence Works

1. **Login Success** → Cookie saved with `email|token`
2. **Page Reload** → Cookie read, session restored
3. **Logout** → Cookie deleted
4. **Cookie Expires** → User must re-authenticate

## Code Structure

### Dependencies

```python
from streamlit_cookies_controller import CookieController
```

**Installation:**
```bash
pip install streamlit-cookies-controller
```

### Key Functions

```python
# Cookie Controller Instance
cookie_controller = CookieController()

# Save session to cookie
def save_session_to_cookie(email: str, token: str):
    """Saves email|token to browser cookie."""
    cookie_controller.set(COOKIE_NAME, f"{email}|{token}")

# Load session from cookie
def load_session_from_cookie() -> tuple[str, str]:
    """Reads and parses cookie if exists."""
    cookie_value = cookie_controller.get(COOKIE_NAME)
    if cookie_value and "|" in cookie_value:
        parts = cookie_value.split("|", 1)
        return parts[0], parts[1]
    return None, None

# Clear session cookie
def clear_session_cookie():
    """Removes cookie on logout."""
    cookie_controller.remove(COOKIE_NAME)

# Login - Authenticates with API
def login(email: str, password: str) -> tuple[bool, str]:
    """
    - Calls LearnX API
    - Stores token in session_state
    - Saves to browser cookie
    Returns: (success, message)
    """

# Logout - Clears all session data
def logout():
    """
    - Clears session_state variables
    - Removes browser cookie
    - Triggers page rerun
    """

# Login Page Display
def show_login_page():
    """Renders the login form UI"""
```

## Security Considerations

### Current Implementation ✅

1. **HTTPS** - API uses HTTPS for secure transmission
2. **Cookie Storage** - Stored in browser, not filesystem
3. **Session Cleanup** - Cookie cleared on explicit logout
4. **7-day Expiry** - Session auto-expires for security

### Recommendations for Production

1. **HttpOnly Cookies** - Set HttpOnly flag to prevent XSS attacks
2. **Secure Flag** - Enable Secure flag for HTTPS-only transmission
3. **Token Expiry** - Implement server-side token validation
4. **Rate Limiting** - Limit login attempts to prevent brute force

## Files Involved

| File | Purpose |
|------|---------|
| `app.py` | Authentication logic (lines 1-110) |
| `requirements.txt` | Contains `streamlit-cookies-controller` |
| `login.html` | Standalone HTML login page (optional) |
| `docs/AUTH.md` | This documentation |

## Usage

### Login
1. Navigate to the application URL
2. Enter email and password
3. Click "Sign In"
4. On success, redirected to main application

### Logout
1. Click the "🚪 Logout" button at the bottom of the sidebar
2. Cookie is cleared
3. Redirected to login page

### Session Persistence
- After successful login, you can refresh the page
- Session will be restored from browser cookie
- Close browser tab: Session persists (cookie still valid)
- Clear browser cookies: Will need to login again
- After 7 days: Cookie expires, must re-login

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Connection timeout" | Check internet connection |
| "Unable to connect to server" | Verify API endpoint is accessible |
| Session not persisting | Check if browser allows cookies |
| Login works but redirects to login | Clear browser cookies and re-login |

### Clearing Session Manually

**In Browser:**
1. Open Developer Tools (F12)
2. Go to Application → Cookies
3. Delete `au_auth_session` cookie

**Or clear all cookies for the site.**

## Environment Variables

No environment variables are required for authentication. The API endpoint is hardcoded in the application.

To modify the API endpoint, update this line in `app.py`:
```python
response = requests.post(
    "https://learnx.atriauniversity.in/api/v1/auth/signin",
    ...
)
```

## Comparison: File vs Cookie Storage

| Feature | File-Based | Cookie-Based ✅ |
|---------|------------|-----------------|
| Persistence | Server restart | Browser refresh |
| Docker Compatible | ❌ No | ✅ Yes |
| Multi-user | ❌ Shared | ✅ Per-browser |
| Security | ⚠️ File access | ✅ Browser sandbox |
| Expiry | Manual | Automatic |
