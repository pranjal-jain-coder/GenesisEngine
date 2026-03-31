import logging
import subprocess
import os
from typing import List, Dict

logger = logging.getLogger(__name__)

class GitManager:
    """Manages local Git repository operations for Genesis Engine projects."""

    @staticmethod
    def _run_git_command(project_path: str, command: List[str]) -> tuple[bool, str]:
        """Runs a Git command in the given project directory."""
        try:
            result = subprocess.run(
                ["git"] + command,
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: git {' '.join(command)}")
            logger.error(f"Error output: {e.stderr.strip()}")
            return False, e.stderr.strip()
        except FileNotFoundError:
            logger.error("Git is not installed or not found in system PATH.")
            return False, "Git is not installed."
        except Exception as e:
            logger.error(f"Unexpected error running Git command: {e}")
            return False, str(e)

    @staticmethod
    def init_repo(project_path: str) -> bool:
        """Initializes a Git repository if it doesn't exist, and creates a basic .gitignore."""
        if not os.path.exists(project_path):
            logger.error(f"Project path does not exist: {project_path}")
            return False

        git_dir = os.path.join(project_path, ".git")
        if os.path.exists(git_dir):
            return True # Already initialized

        logger.info(f"Initializing Git repository in {project_path}")
        success, output = GitManager._run_git_command(project_path, ["init"])
        if not success:
            return False

        # Create Godot 4 standard .gitignore
        gitignore_path = os.path.join(project_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            gitignore_content = """# Godot 4 specific ignores
.godot/
.gdignore

# macOS
.DS_Store

# Genesis Engine internal
tasks.json.tmp
gdd.json.tmp
"""
            try:
                with open(gitignore_path, "w") as f:
                    f.write(gitignore_content)
            except Exception as e:
                logger.error(f"Failed to create .gitignore: {e}")

        # Make initial commit
        GitManager.commit_state(project_path, "Initial Genesis Engine commit")
        return True

    @staticmethod
    def commit_state(project_path: str, message: str) -> bool:
        """Adds all files and makes a commit with the given message."""
        # Ensure repo exists
        if not os.path.exists(os.path.join(project_path, ".git")):
            GitManager.init_repo(project_path)

        # Add all files
        success_add, _ = GitManager._run_git_command(project_path, ["add", "."])
        if not success_add:
            return False

        # Check if there are any changes to commit
        success_status, status_output = GitManager._run_git_command(project_path, ["status", "--porcelain"])
        if success_status and not status_output:
            logger.info(f"No changes to commit for message: '{message}'")
            return True # Nothing to do, but not an error

        # Make commit
        success_commit, commit_output = GitManager._run_git_command(project_path, ["commit", "-m", message])
        if success_commit:
            logger.info(f"Created commit: '{message}'")
            return True
        else:
            logger.error(f"Failed to commit with message: '{message}'. Output: {commit_output}")
            return False

    @staticmethod
    def get_commits(project_path: str) -> List[Dict[str, str]]:
        """Retrieves a list of commits in the repository."""
        if not os.path.exists(os.path.join(project_path, ".git")):
            logger.warning(f"Not a Git repository: {project_path}")
            return []

        # Format: %H (hash), %s (subject/message), %at (author timestamp)
        success, output = GitManager._run_git_command(project_path, ["log", "--pretty=format:%H|%s|%at"])
        if not success:
            return []

        commits = []
        if output:
            for line in output.split("\n"):
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                        "timestamp": parts[2]
                    })
        return commits

    @staticmethod
    def get_head_hash(project_path: str) -> str:
        """Returns the current HEAD commit hash, or an empty string if unavailable."""
        success, output = GitManager._run_git_command(project_path, ["rev-parse", "HEAD"])
        return output if success else ""

    @staticmethod
    def revert_to_commit(project_path: str, commit_hash: str) -> bool:
        """Hard resets the repository to the specified commit hash and cleans untracked files."""
        if not os.path.exists(os.path.join(project_path, ".git")):
            logger.error(f"Cannot revert: Not a Git repository ({project_path})")
            return False

        logger.info(f"Reverting {project_path} to commit {commit_hash}")
        
        # Hard reset
        success_reset, output_reset = GitManager._run_git_command(project_path, ["reset", "--hard", commit_hash])
        if not success_reset:
            logger.error(f"Failed to reset to commit {commit_hash}: {output_reset}")
            return False
            
        # Clean untracked files and directories
        success_clean, output_clean = GitManager._run_git_command(project_path, ["clean", "-fd"])
        if not success_clean:
            logger.warning(f"Failed to clean untracked files after reset: {output_clean}")
            # Still returning True as the reset succeeded
            
        logger.info(f"Successfully reverted to commit {commit_hash}")
        return True
