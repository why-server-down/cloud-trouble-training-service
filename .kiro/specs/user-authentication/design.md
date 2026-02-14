# User Authentication & Profile System - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  Database   │
│  (Auth UI)  │◀─────│  (FastAPI)   │◀─────│ (Postgres)  │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            └─────▶ ┌─────────────┐
                                    │ Kubernetes  │
                                    │  (Create NS)│
                                    └─────────────┘
```

### 1.2 Component Breakdown

**Frontend Components:**
- LoginForm: 로그인 폼
- RegisterForm: 회원가입 폼
- ProfileEditor: 프로필 수정
- SessionManager: 토큰 관리

**Backend Services:**
- AuthService: 인증 처리
- UserService: 사용자 관리
- TokenService: JWT 토큰 관리
- NamespaceService: K8s 네임스페이스 관리

## 2. Data Models

### 2.1 Database Schema

```python
class User(Base):
    id: UUID
    email: str  # Unique, indexed
    password_hash: str
    nickname: str
    profile_image_url: str
    created_at: datetime
    last_login: datetime
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime
    
class UserProfile(Base):
    user_id: UUID
    tier: str
    total_score: int
    missions_completed: int
    achievements_count: int
    
class Session(Base):
    id: UUID
    user_id: UUID
    token: str  # JWT token
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    ip_address: str
    user_agent: str
```

## 3. Core Algorithms

### 3.1 User Registration

```python
class AuthService:
    def __init__(self):
        self.password_hasher = bcrypt
        self.k8s_client = get_k8s_client()
    
    async def register_user(
        self, 
        email: str,
        password: str,
        nickname: str
    ) -> User:
        """
        Registers new user and creates K8s namespace
        """
        # Validate email format
        if not self._is_valid_email(email):
            raise ValidationError("Invalid email format")
        
        # Check if email already exists
        existing = await self.db.query(User).filter(
            User.email == email
        ).first()
        
        if existing:
            raise ValidationError("Email already registered")
        
        # Validate password strength
        if not self._is_strong_password(password):
            raise ValidationError(
                "Password must be at least 8 characters with letters, numbers, and special characters"
            )
        
        # Hash password
        password_hash = self.password_hasher.hashpw(
            password.encode(),
            self.password_hasher.gensalt()
        )
        
        # Create user
        user = User(
            email=email,
            password_hash=password_hash.decode(),
            nickname=nickname,
            created_at=datetime.now(),
            is_active=True,
            failed_login_attempts=0
        )
        await self.db.save(user)
        
        # Create user profile
        profile = UserProfile(
            user_id=user.id,
            tier='Bronze',
            total_score=0,
            missions_completed=0,
            achievements_count=0
        )
        await self.db.save(profile)
        
        # Create K8s namespace
        await self._create_user_namespace(user.id)
        
        return user
    
    def _is_strong_password(self, password: str) -> bool:
        """
        Validates password strength
        """
        if len(password) < 8:
            return False
        
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        
        return has_letter and has_digit and has_special
    
    async def _create_user_namespace(self, user_id: str):
        """
        Creates K8s namespace for user
        """
        namespace_name = f"user-{user_id}"
        
        namespace = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': namespace_name,
                'labels': {
                    'user-id': str(user_id),
                    'managed-by': 'k8s-survival-camp'
                }
            }
        }
        
        try:
            await self.k8s_client.create_namespace(body=namespace)
            
            # Create resource quota
            await self._create_resource_quota(namespace_name)
            
        except Exception as e:
            logger.error(f"Failed to create namespace: {e}")
            raise
    
    async def _create_resource_quota(self, namespace: str):
        """
        Creates resource quota for namespace
        """
        quota = {
            'apiVersion': 'v1',
            'kind': 'ResourceQuota',
            'metadata': {
                'name': 'user-quota',
                'namespace': namespace
            },
            'spec': {
                'hard': {
                    'requests.cpu': '2',
                    'requests.memory': '2Gi',
                    'limits.cpu': '4',
                    'limits.memory': '4Gi',
                    'pods': '10'
                }
            }
        }
        
        await self.k8s_client.create_namespaced_resource_quota(
            namespace=namespace,
            body=quota
        )
```

### 3.2 User Login

```python
class AuthService:
    async def login(
        self, 
        email: str, 
        password: str,
        ip_address: str,
        user_agent: str
    ) -> LoginResponse:
        """
        Authenticates user and returns JWT token
        """
        # Get user
        user = await self.db.query(User).filter(
            User.email == email
        ).first()
        
        if not user:
            raise AuthenticationError("Invalid email or password")
        
        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now():
            remaining = (user.locked_until - datetime.now()).seconds // 60
            raise AuthenticationError(
                f"Account locked. Try again in {remaining} minutes"
            )
        
        # Verify password
        if not self.password_hasher.checkpw(
            password.encode(),
            user.password_hash.encode()
        ):
            # Increment failed attempts
            user.failed_login_attempts += 1
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now() + timedelta(minutes=10)
            
            await self.db.save(user)
            raise AuthenticationError("Invalid email or password")
        
        # Reset failed attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now()
        await self.db.save(user)
        
        # Generate JWT token
        token = await self.token_service.create_token(user.id)
        
        # Create session
        session = Session(
            user_id=user.id,
            token=token,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
            last_activity=datetime.now(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        await self.db.save(session)
        
        return LoginResponse(
            token=token,
            user=UserResponse.from_orm(user),
            expires_in=86400  # 24 hours
        )
```

### 3.3 JWT Token Management

```python
class TokenService:
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET_KEY')
        self.algorithm = 'HS256'
    
    async def create_token(self, user_id: str) -> str:
        """
        Creates JWT token
        """
        payload = {
            'user_id': str(user_id),
            'exp': datetime.utcnow() + timedelta(hours=24),
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token
    
    async def verify_token(self, token: str) -> str:
        """
        Verifies JWT token and returns user_id
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload['user_id']
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
    
    async def refresh_token(self, old_token: str) -> str:
        """
        Refreshes JWT token
        """
        user_id = await self.verify_token(old_token)
        return await self.create_token(user_id)
```

### 3.4 Session Management

```python
class SessionManager:
    async def update_activity(self, token: str):
        """
        Updates last activity timestamp
        """
        session = await self.db.query(Session).filter(
            Session.token == token
        ).first()
        
        if session:
            session.last_activity = datetime.now()
            await self.db.save(session)
    
    async def cleanup_expired_sessions(self):
        """
        Removes expired sessions
        Runs every hour
        """
        expired = await self.db.query(Session).filter(
            Session.expires_at < datetime.now()
        ).all()
        
        for session in expired:
            await self.db.delete(session)
    
    async def check_inactivity(self, token: str) -> bool:
        """
        Checks if session is inactive for 30 minutes
        """
        session = await self.db.query(Session).filter(
            Session.token == token
        ).first()
        
        if not session:
            return True
        
        inactive_duration = datetime.now() - session.last_activity
        return inactive_duration > timedelta(minutes=30)
```

### 3.5 Profile Management

```python
class UserService:
    async def update_profile(
        self,
        user_id: str,
        nickname: str = None,
        profile_image: UploadFile = None
    ) -> User:
        """
        Updates user profile
        """
        user = await self.get_user(user_id)
        
        if nickname:
            # Validate nickname
            if len(nickname) < 2 or len(nickname) > 20:
                raise ValidationError("Nickname must be 2-20 characters")
            
            user.nickname = nickname
        
        if profile_image:
            # Upload image to storage
            image_url = await self.storage_service.upload_image(
                profile_image,
                f"profiles/{user_id}"
            )
            user.profile_image_url = image_url
        
        await self.db.save(user)
        return user
    
    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ):
        """
        Changes user password
        """
        user = await self.get_user(user_id)
        
        # Verify current password
        if not self.password_hasher.checkpw(
            current_password.encode(),
            user.password_hash.encode()
        ):
            raise AuthenticationError("Current password is incorrect")
        
        # Validate new password
        if not self._is_strong_password(new_password):
            raise ValidationError("New password is not strong enough")
        
        # Hash new password
        new_hash = self.password_hasher.hashpw(
            new_password.encode(),
            self.password_hasher.gensalt()
        )
        
        user.password_hash = new_hash.decode()
        await self.db.save(user)
```

## 4. API Endpoints

```python
@router.post("/api/auth/register")
async def register(request: RegisterRequest):
    """
    Registers new user
    """
    user = await auth_service.register_user(
        request.email,
        request.password,
        request.nickname
    )
    
    # Auto-login
    login_response = await auth_service.login(
        request.email,
        request.password,
        request.ip_address,
        request.user_agent
    )
    
    return login_response

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    """
    Logs in user
    """
    return await auth_service.login(
        request.email,
        request.password,
        request.ip_address,
        request.user_agent
    )

@router.post("/api/auth/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logs out user
    """
    await session_manager.invalidate_session(current_user.token)
    return {"message": "Logged out successfully"}

@router.get("/api/users/me")
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Gets current user's profile
    """
    profile = await user_service.get_profile(current_user.id)
    return UserProfileResponse.from_orm(current_user, profile)

@router.put("/api/users/me")
async def update_profile(
    nickname: str = Form(None),
    profile_image: UploadFile = File(None),
    current_user: User = Depends(get_current_user)
):
    """
    Updates user profile
    """
    user = await user_service.update_profile(
        current_user.id,
        nickname,
        profile_image
    )
    return UserResponse.from_orm(user)

@router.post("/api/users/me/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Changes password
    """
    await user_service.change_password(
        current_user.id,
        request.current_password,
        request.new_password
    )
    return {"message": "Password changed successfully"}
```

## 5. Authentication Middleware

```python
async def get_current_user(
    authorization: str = Header(None)
) -> User:
    """
    Dependency for protected endpoints
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, "Missing or invalid authorization header")
    
    token = authorization.split(' ')[1]
    
    # Verify token
    try:
        user_id = await token_service.verify_token(token)
    except AuthenticationError as e:
        raise HTTPException(401, str(e))
    
    # Check session inactivity
    if await session_manager.check_inactivity(token):
        raise HTTPException(401, "Session expired due to inactivity")
    
    # Update activity
    await session_manager.update_activity(token)
    
    # Get user
    user = await user_service.get_user(user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    
    return user
```

## 6. Security Considerations

- Passwords hashed with bcrypt (cost factor 12)
- JWT tokens signed with HS256
- Account lockout after 5 failed attempts
- Session timeout after 30 minutes of inactivity
- HTTPS only in production
- CORS configured for frontend domain only

## 7. Testing Strategy

### Property-Based Tests
- Property: Password hash is never equal to plaintext password
- Property: JWT token always expires after 24 hours
- Property: Failed login attempts increment correctly
- Property: Account locks after exactly 5 failed attempts
