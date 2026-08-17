# 🐛 Debug & Monitor Guide for eTax Platform

This guide shows you how to inspect every part of your application - logs, database, API requests, and real-time monitoring.

---

## **1. BACKEND LOGS (What the server is doing)**

### Option A: View logs in real-time with docker-compose

```powershell
cd "c:\Users\Ali Ahmed\OneDrive - Alexandria National University\Desktop\Etax\Ai-assisted tax platform"
docker compose logs -f backend
```

**What you'll see:**
- Every HTTP request
- Database operations
- Errors and exceptions


### Option B: View logs from a specific container

```powershell
# List running containers
docker ps

# View logs (replace with your container name)
docker logs <container-name> -f
```

**Example output:**
```
INFO:app.auth.routes:🔐 SIGNUP REQUEST: username=john_doe, email=john@example.com
INFO:app.auth.routes:✅ USER CREATED: id=550e8400-e29b-41d4-a716-446655440000, username=john_doe
INFO:app.auth.routes:🎫 TOKEN ISSUED: user_id=550e8400-e29b-41d4-a716-446655440000, stage=pending_enrollment
```

**Log Symbols Explained:**
- 🔐 = Authentication attempt
- 🔓 = Login attempt
- 🎬 = Face enrollment started
- 🔐 = Face verification started
- 🔍 = Face detection/analysis
- ✅ = Success
- ❌ = Failure/Error
- 📷 = Image processing
- 💾 = Database save
- 📊 = Statistics/Score

---

## **2. TEST API REQUESTS (Try endpoints live)**

### Easiest: Use FastAPI Swagger UI

1. **Start the app:**
   ```powershell
   docker compose up
   ```

2. **Open in browser:**
   ```
   http://localhost:8000/docs
   ```

3. **Click any endpoint** (e.g., `POST /auth/signup`)

4. **Click "Try it out"**

5. **Fill in test data:**
   ```json
   {
     "full_name": "John Doe",
     "username": "johndoe",
     "email": "john@example.com",
     "password": "SecurePassword123!"
   }
   ```

6. **Click "Execute"**

7. **See response + status code**

**Watch the backend logs simultaneously** to see the logging output!

---

## **3. DATABASE INSPECTION**

### Option A: Using PostgreSQL CLI (psql)

**Enter the database:**
```powershell
docker compose exec db psql -U etax -d etax
```

**Useful queries:**

```sql
-- 📋 See all users
SELECT id, username, email, full_name, is_active, created_at FROM users;

-- 👤 See a specific user
SELECT * FROM users WHERE username = 'johndoe';

-- 🎯 See how many users exist
SELECT COUNT(*) as total_users FROM users;

-- 🖼️  See all face profiles (enrolled faces)
SELECT fp.id, fp.user_id, u.username, fp.created_at 
FROM face_profiles fp
JOIN users u ON fp.user_id = u.id;

-- 🎯 Check if a user has enrolled a face
SELECT * FROM face_profiles WHERE user_id = '550e8400-e29b-41d4-a716-446655440000';

-- 📊 See embedding dimensions (should be 512)
SELECT array_length(embedding, 1) as embedding_dim 
FROM face_profiles LIMIT 1;

-- 🗑️  Delete a test user and cascade delete face profile
DELETE FROM users WHERE username = 'johndoe';

-- Exit psql
\q
```

### Option B: VS Code Database Extension (Visual)

**Install in VS Code:**
1. Open VS Code
2. Go to Extensions
3. Search: "Database Client" or "PostgreSQL"
4. Click Install

**Connect to database:**
1. Press `Ctrl+Shift+P`
2. Type "Database: Add Connection"
3. Choose PostgreSQL
4. Fill in:
   - Host: `localhost`
   - Port: `5432`
   - Username: `etax`
   - Password: `etax_pw`
   - Database: `etax`

**Now you can:**
- Click "Database" in sidebar
- See tables in tree view
- Right-click table → "Edit Records"
- Right-click table → "Run Query"

---

## **4. FULL REQUEST FLOW EXAMPLE**

Let's trace a complete signup + face enrollment:

### Step 1: Monitor logs
```powershell
docker compose logs -f backend
```

### Step 2: Test signup via Swagger
1. Go to `http://localhost:8000/docs`
2. POST `/auth/signup`
3. Try it out with:
   ```json
   {
     "full_name": "Alice Smith",
     "username": "alice123",
     "email": "alice@example.com",
     "password": "MyPassword456!"
   }
   ```

### Step 3: Watch logs in real-time
```
INFO:app.auth.routes:🔐 SIGNUP REQUEST: username=alice123, email=alice@example.com
INFO:app.auth.routes:✅ USER CREATED: id=abc123..., username=alice123
INFO:app.auth.routes:🎫 TOKEN ISSUED: user_id=abc123..., stage=pending_enrollment
```

### Step 4: Check database
```powershell
docker compose exec db psql -U etax -d etax
```

```sql
SELECT id, username, email, created_at FROM users WHERE username = 'alice123';
```

**Output:**
```
                  id                  | username |      email       |         created_at         
--------------------------------------+----------+------------------+----------------------------
 abc12345-e29b-41d4-a716-446655440000 | alice123 | alice@example.com | 2026-08-16 10:30:45.123456
(1 row)
```

### Step 5: Copy the token from signup response

In Swagger, copy the `access_token` from the response.

### Step 6: Test face enrollment
1. POST `/face/enroll`
2. Click "Try it out"
3. Paste token in `Authorization` header (format: `Bearer <token>`)
4. Upload a face image

### Step 7: Watch logs
```
INFO:app.face.routes:🎬 FACE ENROLLMENT REQUEST: user_id=abc123..., username=alice123
INFO:app.face.routes:📷 Reading image data for user_id=abc123...
INFO:app.face.routes:🔍 Detecting face for user_id=abc123...
INFO:app.face.routes:✅ Face detected and liveness verified for user_id=abc123...
INFO:app.face.routes:💾 Saving face embedding (512-dim vector) to database
INFO:app.face.routes:✅ FACE PROFILE SAVED: user_id=abc123...
INFO:app.face.routes:🎫 AUTHENTICATED TOKEN ISSUED: user_id=abc123...
```

### Step 8: Verify in database
```sql
SELECT fp.id, fp.user_id, u.username, fp.created_at 
FROM face_profiles fp
JOIN users u ON fp.user_id = u.id
WHERE u.username = 'alice123';
```

**Output:**
```
 id |                user_id                | username |         created_at         
----+--------------------------------------+----------+----------------------------
  1 | abc12345-e29b-41d4-a716-446655440000 | alice123 | 2026-08-16 10:31:02.654321
(1 row)
```

---

## **5. QUICK REFERENCE COMMANDS**

### Start everything
```powershell
docker compose up
```

### View all logs
```powershell
docker compose logs -f
```

### View only backend logs
```powershell
docker compose logs -f backend
```

### View only database logs
```powershell
docker compose logs -f db
```

### Access database CLI
```powershell
docker compose exec db psql -U etax -d etax
```

### Clean start (delete old data)
```powershell
docker compose down -v
docker compose up --build
```

### Stop everything
```powershell
docker compose down
```

### Rebuild only backend (after code changes)
```powershell
docker compose up --build backend
```

---

## **6. UNDERSTANDING LOG LEVELS**

In Python logging:
- **INFO** (ℹ️) = Normal operation flow
- **WARNING** (⚠️) = Something unexpected but not critical
- **ERROR** (❌) = Error occurred
- **DEBUG** (🔍) = Detailed diagnostic information

---

## **7. COMMON DEBUGGING SCENARIOS**

### Scenario 1: "User login fails"

**Check logs:**
```powershell
docker compose logs -f backend
```

Look for:
```
❌ LOGIN FAILED: invalid credentials for alice123
```

**Check database:**
```sql
SELECT username, email, is_active FROM users WHERE username = 'alice123';
```

Verify user exists and is_active = true.

---

### Scenario 2: "Face enrollment fails"

**Check logs for:**
```
❌ No face detected. Position your face inside the frame.
```
or
```
❌ Liveness check failed. This looks like a photo...
```

This means:
- Either no face was detected in the image
- Or the liveness check rejected it (e.g., showing a photo instead of live face)

---

### Scenario 3: "Face verification fails"

**Check logs:**
```
📊 FACE SIMILARITY SCORE: user_id=abc..., similarity=0.3210, threshold=0.4500
❌ VERIFICATION FAILED: Face match score too low (0.3210)
```

This means the captured face didn't match the enrolled face enough. The similarity was 0.3210 but needs to be ≥ 0.4500.

**Why?**
- Different lighting
- Different angle
- Poor image quality
- Different person

---

## **8. PERFORMANCE MONITORING**

### Check database size
```sql
-- Size of users table
SELECT pg_size_pretty(pg_total_relation_size('users'));

-- Size of face_profiles table
SELECT pg_size_pretty(pg_total_relation_size('face_profiles'));

-- Total database size
SELECT pg_size_pretty(pg_database_size('etax'));
```

### Check slow queries
Enable query logging (advanced) - see PostgreSQL documentation.

---

## **9. EXPORTING DATA FOR ANALYSIS**

### Export users to CSV
```powershell
docker compose exec db psql -U etax -d etax -c "COPY users TO STDOUT WITH CSV HEADER" > users.csv
```

### Export all data
```powershell
docker compose exec db pg_dump -U etax etax > backup.sql
```

---

## **Summary**

| What to monitor | Tool | Command |
|---|---|---|
| Backend logs | Docker | `docker compose logs -f backend` |
| API testing | Browser | `http://localhost:8000/docs` |
| Database | psql CLI | `docker compose exec db psql -U etax -d etax` |
| Database (GUI) | VS Code | Install "Database Client" extension |
| All logs | Docker | `docker compose logs -f` |

**Happy debugging! 🚀**
