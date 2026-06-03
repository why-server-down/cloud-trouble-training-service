import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class CommandResult:
    output: str
    exit_code: int
    execution_time: float  # milliseconds


class CommandExecutor:
    DEFAULT_TIMEOUT = 5  # seconds

    async def execute(self, command: str, timeout: int | None = None) -> CommandResult:
        timeout = timeout or self.DEFAULT_TIMEOUT
        start_time = time.time()

        try:
            # Windows에서는 subprocess.run을 asyncio.to_thread로 실행
            if sys.platform == 'win32':
                result = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    shell=True,
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )
                
                execution_time = (time.time() - start_time) * 1000
                output = result.stdout if result.stdout else result.stderr
                
                print(f"📊 Command output (exit_code={result.returncode}):")
                print(f"   stdout: {result.stdout if result.stdout else '(empty)'}")
                print(f"   stderr: {result.stderr if result.stderr else '(empty)'}")
                
                return CommandResult(
                    output=output,
                    exit_code=result.returncode,
                    execution_time=execution_time,
                )
            
            # Unix/Linux에서는 기존 방식 사용
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            execution_time = (time.time() - start_time) * 1000
            output = stdout.decode() if stdout else stderr.decode()
            
            print(f"📊 Command output (exit_code={process.returncode}):")
            print(f"   stdout: {stdout.decode() if stdout else '(empty)'}")
            print(f"   stderr: {stderr.decode() if stderr else '(empty)'}")

            return CommandResult(
                output=output,
                exit_code=process.returncode or 0,
                execution_time=execution_time,
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return CommandResult(
                output=f"Command timed out after {timeout} seconds",
                exit_code=124,
                execution_time=timeout * 1000,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_output = f"Error executing command: {type(e).__name__}: {str(e)}"
            print(f"❌ Exception during execution:")
            print(f"   Type: {type(e).__name__}")
            print(f"   Message: {str(e)}")
            print(f"   Full error: {repr(e)}")
            import traceback
            traceback.print_exc()
            return CommandResult(
                output=error_output,
                exit_code=1,
                execution_time=execution_time,
            )
