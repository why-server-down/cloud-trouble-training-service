# Web Terminal Interface - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│ Kubernetes  │
│  (xterm.js) │◀─────│  (WebSocket) │◀─────│   Client    │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            └─────▶ ┌─────────────┐
                                    │  Database   │
                                    │  (Logs)     │
                                    └─────────────┘
```

### 1.2 Component Breakdown

**Frontend Components:**
- TerminalUI: xterm.js 기반 터미널 렌더링
- CommandAutocomplete: kubectl 명령어 자동완성
- SessionManager: WebSocket 연결 관리
- ShareDialog: 세션 공유 UI

**Backend Services:**
- WebSocketHandler: WebSocket 연결 처리
- CommandExecutor: kubectl 명령어 실행
- CommandValidator: 명령어 검증 및 필터링
- SessionManager: 세션 관리
- CommandLogger: 명령어 실행 로그

## 2. Data Models

### 2.1 Database Schema

```python
class TerminalSession(Base):
    id: UUID
    user_id: UUID
    namespace: str
    created_at: datetime
    last_activity: datetime
    is_active: bool
    share_token: str  # For session sharing
    
class CommandLog(Base):
    id: UUID
    session_id: UUID
    command: str
    output: str
    exit_code: int
    executed_at: datetime
    execution_time: float  # milliseconds
```

### 2.2 WebSocket Message Format

```python
# Client -> Server
class CommandMessage:
    type: str = "command"
    command: str
    session_id: str

# Server -> Client
class OutputMessage:
    type: str = "output"
    data: str
    exit_code: int
    execution_time: float

class ErrorMessage:
    type: str = "error"
    message: str
    code: str  # 'INVALID_COMMAND', 'TIMEOUT', 'PERMISSION_DENIED'
```

## 3. Core Algorithms

### 3.1 Command Validation

```python
class CommandValidator:
    # Whitelist of allowed kubectl commands
    ALLOWED_COMMANDS = [
        'get', 'describe', 'logs', 'edit', 'apply', 'delete',
        'exec', 'port-forward', 'top', 'explain'
    ]
    
    # Blacklist of dangerous patterns
    BLACKLIST_PATTERNS = [
        r'\|',  # Pipe
        r'>',   # Redirect
        r'<',   # Redirect
        r'&&',  # Command chaining
        r';',   # Command separator
        r'`',   # Command substitution
        r'\$\(',  # Command substitution
    ]
    
    def validate_command(self, command: str, namespace: str) -> ValidationResult:
        """
        Validates kubectl command
        Returns ValidationResult with is_valid and error_message
        """
        # Check if command starts with kubectl
        if not command.strip().startswith('kubectl'):
            return ValidationResult(
                is_valid=False,
                error="Only kubectl commands are allowed"
            )
        
        # Parse command
        parts = command.split()
        if len(parts) < 2:
            return ValidationResult(
                is_valid=False,
                error="Invalid kubectl command"
            )
        
        # Check if subcommand is allowed
        subcommand = parts[1]
        if subcommand not in self.ALLOWED_COMMANDS:
            return ValidationResult(
                is_valid=False,
                error=f"Command '{subcommand}' is not allowed"
            )
        
        # Check for dangerous patterns
        for pattern in self.BLACKLIST_PATTERNS:
            if re.search(pattern, command):
                return ValidationResult(
                    is_valid=False,
                    error="Command contains forbidden characters"
                )
        
        # Check for dangerous delete operations
        if subcommand == 'delete':
            if not self._confirm_delete(command):
                return ValidationResult(
                    is_valid=False,
                    error="Delete operation requires confirmation",
                    requires_confirmation=True
                )
        
        # Inject namespace if not specified
        if '-n' not in command and '--namespace' not in command:
            command = self._inject_namespace(command, namespace)
        
        # Verify namespace matches user's namespace
        if not self._verify_namespace(command, namespace):
            return ValidationResult(
                is_valid=False,
                error=f"Access denied: You can only access namespace '{namespace}'"
            )
        
        return ValidationResult(is_valid=True, command=command)
    
    def _inject_namespace(self, command: str, namespace: str) -> str:
        """
        Injects namespace into kubectl command
        """
        parts = command.split()
        # Insert after 'kubectl <subcommand>'
        parts.insert(2, f'-n {namespace}')
        return ' '.join(parts)
    
    def _verify_namespace(self, command: str, allowed_namespace: str) -> bool:
        """
        Verifies command only accesses allowed namespace
        """
        # Extract namespace from command
        match = re.search(r'-n\s+(\S+)|--namespace[=\s]+(\S+)', command)
        if match:
            namespace = match.group(1) or match.group(2)
            return namespace == allowed_namespace
        
        return True  # No namespace specified, will use default
```

### 3.2 Command Execution

```python
class CommandExecutor:
    def __init__(self):
        self.k8s_config = config.load_kube_config()
    
    async def execute_command(
        self, 
        command: str,
        timeout: int = 5
    ) -> CommandResult:
        """
        Executes kubectl command
        Timeout: 5 seconds
        """
        start_time = time.time()
        
        try:
            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            # Decode output
            output = stdout.decode() if stdout else stderr.decode()
            
            return CommandResult(
                output=output,
                exit_code=process.returncode,
                execution_time=execution_time
            )
            
        except asyncio.TimeoutError:
            # Kill process
            process.kill()
            await process.wait()
            
            return CommandResult(
                output="Command timed out after 5 seconds",
                exit_code=124,
                execution_time=5000
            )
        
        except Exception as e:
            return CommandResult(
                output=f"Error executing command: {str(e)}",
                exit_code=1,
                execution_time=(time.time() - start_time) * 1000
            )
```

### 3.3 WebSocket Handler

```python
class WebSocketHandler:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.command_validator = CommandValidator()
        self.command_executor = CommandExecutor()
    
    async def handle_connection(
        self, 
        websocket: WebSocket,
        user_id: str,
        session_id: str
    ):
        """
        Handles WebSocket connection for terminal session
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        
        # Get user's namespace
        namespace = f"user-{user_id}"
        
        # Send welcome message
        await self.send_output(
            websocket,
            f"Connected to namespace: {namespace}\n"
            f"Type 'kubectl' commands to interact with your cluster.\n\n"
        )
        
        try:
            while True:
                # Receive command from client
                data = await websocket.receive_json()
                
                if data['type'] == 'command':
                    await self.handle_command(
                        websocket,
                        data['command'],
                        namespace,
                        session_id
                    )
                
        except WebSocketDisconnect:
            del self.active_connections[session_id]
            await self.cleanup_session(session_id)
    
    async def handle_command(
        self,
        websocket: WebSocket,
        command: str,
        namespace: str,
        session_id: str
    ):
        """
        Handles command execution
        """
        # Validate command
        validation = self.command_validator.validate_command(command, namespace)
        
        if not validation.is_valid:
            await self.send_error(websocket, validation.error)
            return
        
        # Execute command
        result = await self.command_executor.execute_command(
            validation.command,
            timeout=5
        )
        
        # Send output to client
        await self.send_output(
            websocket,
            result.output,
            result.exit_code,
            result.execution_time
        )
        
        # Log command
        await self.log_command(session_id, command, result)
    
    async def send_output(
        self,
        websocket: WebSocket,
        data: str,
        exit_code: int = 0,
        execution_time: float = 0
    ):
        """
        Sends command output to client
        """
        await websocket.send_json({
            'type': 'output',
            'data': data,
            'exit_code': exit_code,
            'execution_time': execution_time
        })
    
    async def send_error(self, websocket: WebSocket, message: str):
        """
        Sends error message to client
        """
        await websocket.send_json({
            'type': 'error',
            'message': message
        })
```

### 3.4 Command Autocomplete

```typescript
// Frontend: CommandAutocomplete.ts
export class CommandAutocomplete {
  private kubectl_commands = [
    'kubectl get pods',
    'kubectl get services',
    'kubectl get deployments',
    'kubectl describe pod',
    'kubectl logs',
    'kubectl edit',
    'kubectl apply -f',
    'kubectl delete pod'
  ];
  
  getSuggestions(input: string): string[] {
    if (!input.startsWith('kubectl')) {
      return [];
    }
    
    return this.kubectl_commands.filter(cmd => 
      cmd.startsWith(input)
    );
  }
  
  async getResourceNames(resourceType: string): Promise<string[]> {
    // Fetch resource names from backend
    const response = await fetch(`/api/terminal/resources/${resourceType}`);
    return response.json();
  }
}
```

### 3.5 Session Sharing

```python
class SessionSharingService:
    async def create_share_link(
        self, 
        session_id: str,
        user_id: str
    ) -> str:
        """
        Creates shareable link for terminal session
        """
        # Generate share token
        share_token = secrets.token_urlsafe(32)
        
        # Update session
        session = await self.get_session(session_id)
        session.share_token = share_token
        await self.db.save(session)
        
        # Set expiration (30 minutes)
        await self.redis.setex(
            f"share:{share_token}",
            1800,  # 30 minutes
            session_id
        )
        
        return f"https://app.k8s-survival.com/terminal/share/{share_token}"
    
    async def join_shared_session(
        self,
        share_token: str,
        websocket: WebSocket
    ):
        """
        Joins shared terminal session (read-only)
        """
        # Verify token
        session_id = await self.redis.get(f"share:{share_token}")
        if not session_id:
            raise HTTPException(404, "Share link expired or invalid")
        
        # Connect to session (read-only)
        await websocket.accept()
        
        # Subscribe to session output
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"session:{session_id}:output")
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    await websocket.send_text(message['data'])
        except WebSocketDisconnect:
            await pubsub.unsubscribe(f"session:{session_id}:output")
```

## 4. API Endpoints

```python
@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(
    websocket: WebSocket,
    session_id: str,
    current_user: User = Depends(get_current_user_ws)
):
    """
    WebSocket endpoint for terminal
    """
    await websocket_handler.handle_connection(
        websocket,
        current_user.id,
        session_id
    )

@router.post("/api/terminal/sessions")
async def create_session(current_user: User = Depends(get_current_user)):
    """
    Creates new terminal session
    """
    session = TerminalSession(
        user_id=current_user.id,
        namespace=f"user-{current_user.id}",
        created_at=datetime.now(),
        is_active=True
    )
    await db.save(session)
    
    return SessionResponse(session_id=session.id)

@router.post("/api/terminal/sessions/{session_id}/share")
async def share_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Creates shareable link for session
    """
    share_link = await session_sharing_service.create_share_link(
        session_id,
        current_user.id
    )
    
    return ShareResponse(share_link=share_link)

@router.get("/api/terminal/resources/{resource_type}")
async def get_resources(
    resource_type: str,
    current_user: User = Depends(get_current_user)
):
    """
    Gets resource names for autocomplete
    """
    namespace = f"user-{current_user.id}"
    resources = await k8s_client.list_resources(resource_type, namespace)
    
    return [r.metadata.name for r in resources]
```

## 5. Frontend Implementation

```typescript
// Terminal.tsx
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';

export function TerminalComponent({ sessionId }: Props) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal>();
  const ws = useRef<WebSocket>();
  
  useEffect(() => {
    // Initialize terminal
    terminal.current = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace'
    });
    
    const fitAddon = new FitAddon();
    terminal.current.loadAddon(fitAddon);
    terminal.current.open(terminalRef.current!);
    fitAddon.fit();
    
    // Connect WebSocket
    ws.current = new WebSocket(`ws://localhost:8000/ws/terminal/${sessionId}`);
    
    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'output') {
        terminal.current?.write(message.data);
      } else if (message.type === 'error') {
        terminal.current?.write(`\r\n\x1b[31mError: ${message.message}\x1b[0m\r\n`);
      }
    };
    
    // Handle user input
    let currentLine = '';
    terminal.current.onData((data) => {
      if (data === '\r') {
        // Enter pressed
        terminal.current?.write('\r\n');
        ws.current?.send(JSON.stringify({
          type: 'command',
          command: currentLine
        }));
        currentLine = '';
      } else if (data === '\u007F') {
        // Backspace
        if (currentLine.length > 0) {
          currentLine = currentLine.slice(0, -1);
          terminal.current?.write('\b \b');
        }
      } else {
        currentLine += data;
        terminal.current?.write(data);
      }
    });
    
    return () => {
      ws.current?.close();
      terminal.current?.dispose();
    };
  }, [sessionId]);
  
  return <div ref={terminalRef} style={{ height: '100%' }} />;
}
```

## 6. Security Considerations

- Command whitelist prevents dangerous operations
- Namespace isolation prevents cross-user access
- Session timeout after 30 minutes of inactivity
- Share links expire after 30 minutes
- All commands logged for audit

## 7. Testing Strategy

### Property-Based Tests
- Property: All commands are prefixed with namespace
- Property: Dangerous patterns are always blocked
- Property: Command execution completes within timeout
- Property: Session cleanup removes all resources
