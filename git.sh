#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-v0.0.2}"
MESSAGE="${2:-dashboard ${VERSION}}"
REPO_URL="${3:-git@github.com:proxierdima/dashboard.git}"
DEFAULT_BRANCH="main"

# Файлы/папки, которые нельзя публиковать
BLOCKED_REGEX='(^|/)\.env($|\.|/)|(^|/).*\.db$|(^|/).*\.sqlite$|(^|/).*\.sqlite3$|(^|/).*\.log$|(^|/).*\.pyc$|(^|/)__pycache__(/|$)|(^|/).*\.rej$|(^|/)\.venv(/|$)|(^|/)venv(/|$)'

# Если git ещё не инициализирован — инициализируем и добавляем remote
if [ ! -d .git ]; then
  git init
  git branch -M "$DEFAULT_BRANCH"
  git remote add origin "$REPO_URL"
else
  # Если origin не настроен — добавим
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "$REPO_URL"
  fi
fi

# Создаём .gitignore если его нет
if [ ! -f .gitignore ]; then
  cat > .gitignore <<'GITIGNORE'
.env
*.env
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.venv/
venv/
*.db
*.sqlite
*.sqlite3
*.log
*.rej
.DS_Store
GITIGNORE
fi

# Удаляем из индекса то, что должно игнорироваться, если ранее уже попало в git
for pathspec in '.env' '*.env' '*.db' '*.sqlite' '*.sqlite3' '*.log' '*.pyc' '*.rej' '__pycache__' '.venv' 'venv'; do
  git rm -r --cached --ignore-unmatch $pathspec >/dev/null 2>&1 || true
done

# Добавляем файлы
git add .

# Проверяем staged на запрещённые артефакты
STAGED_FILES="$(git diff --cached --name-only || true)"
if echo "$STAGED_FILES" | grep -E "$BLOCKED_REGEX" >/dev/null 2>&1; then
  echo "ERROR: blocked files detected in staged changes:"
  echo "$STAGED_FILES" | grep -E "$BLOCKED_REGEX" || true
  echo
  echo "Fix them and rerun."
  exit 1
fi

# Коммитим, если есть изменения
if ! git diff --cached --quiet; then
  git commit -m "$MESSAGE"
else
  echo "Nothing staged for commit"
fi

# Проверяем, существует ли удалённая ветка main
if git ls-remote --exit-code --heads origin "$DEFAULT_BRANCH" >/dev/null 2>&1; then
  git pull --rebase origin "$DEFAULT_BRANCH"
  git push origin "$DEFAULT_BRANCH"
else
  git push -u origin "$DEFAULT_BRANCH"
fi

# Создаём и пушим тег, если его ещё нет локально
if ! git rev-parse "$VERSION" >/dev/null 2>&1; then
  git tag "$VERSION"
fi

git push origin "$VERSION"

echo

echo "Done: pushed to origin/$DEFAULT_BRANCH and tag $VERSION"

