import asyncio
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
            return CommandResult(
                output=f"Error executing command: {str(e)}",
                exit_code=1,
                execution_time=execution_time,
            )
