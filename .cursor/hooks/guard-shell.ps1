$ErrorActionPreference = "Stop"

function Write-HookDecision {
    param(
        [string]$Permission,
        [string]$UserMessage,
        [string]$AgentMessage
    )

    $payload = [ordered]@{
        permission = $Permission
    }
    if ($UserMessage) {
        $payload.user_message = $UserMessage
    }
    if ($AgentMessage) {
        $payload.agent_message = $AgentMessage
    }
    $payload | ConvertTo-Json -Compress
    exit 0
}

$rawInput = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($rawInput)) {
    Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage ""
}

try {
    $payload = $rawInput | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage "Hook input JSON parsing failed; allowing command because automatic shell approval gates are disabled for this project."
}

$command = ""
if ($payload.PSObject.Properties.Name -contains "command") {
    $command = [string]$payload.command
} elseif ($payload.PSObject.Properties.Name -contains "shell_command") {
    $command = [string]$payload.shell_command
} elseif ($payload.PSObject.Properties.Name -contains "input") {
    $inputObject = $payload.input
    if ($inputObject -and $inputObject.PSObject.Properties.Name -contains "command") {
        $command = [string]$inputObject.command
    }
}

if ([string]::IsNullOrWhiteSpace($command)) {
    Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage ""
}

$lowerCommand = $command.ToLowerInvariant()
$secretPatterns = @(
    'sk-[A-Za-z0-9_-]{20,}',
    '(?i)(LLM_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|TUSHARE_TOKEN)\s*=\s*["'']?[^"''\s]{12,}'
)

foreach ($pattern in $secretPatterns) {
    if ($command -match $pattern) {
        Write-HookDecision -Permission "deny" -UserMessage "Blocked: the shell command appears to contain an API key or token. Put secrets in .env and keep .env ignored by Git." -AgentMessage "Do not run shell commands that expose raw secrets. Use .env or environment variables outside committed files."
    }
}

if (($lowerCommand -match '\bgit\s+add\b') -and ($lowerCommand -match '(^|[\\/\s"''])\.env($|[\s"''])')) {
    Write-HookDecision -Permission "deny" -UserMessage "Blocked: .env must not be staged or committed." -AgentMessage "Refuse git add .env. Use .env.example for safe placeholders."
}

if ($lowerCommand -match '\bgit\s+add\s+(\.|-a\b|--all\b)') {
    Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage "Broad git add detected. Automatic approval is enabled; run a focused secret scan before committing."
}

$dangerousGitPatterns = @(
    '\bgit\s+push\b.*(\s--force\b|\s-f\b|\s--force-with-lease\b)',
    '\bgit\s+reset\b.*\s--hard\b',
    '\bgit\s+clean\b.*(\s-[^\s]*f|\s--force\b)',
    '\bgit\s+checkout\b.*\s--\s'
)

foreach ($pattern in $dangerousGitPatterns) {
    if ($lowerCommand -match $pattern) {
        Write-HookDecision -Permission "deny" -UserMessage "Blocked: destructive or history-rewriting Git command detected. Ask the user explicitly before using this operation." -AgentMessage "Do not run destructive Git commands without explicit approval."
    }
}

if ($lowerCommand -match '\b(rm\s+-rf|remove-item\b.*(-recurse|-force))') {
    Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage "Recursive or force deletion detected. Automatic approval is enabled; use destructive commands only when intentionally requested."
}

Write-HookDecision -Permission "allow" -UserMessage "" -AgentMessage ""
