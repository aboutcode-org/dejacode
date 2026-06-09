#!/usr/bin/env bash
# DejaCode installer — no root required, works on macOS and Linux.
# Usage: curl -sSL https://raw.githubusercontent.com/aboutcode-org/dejacode/main/install.sh | bash
set -eu

REPO="https://raw.githubusercontent.com/aboutcode-org/dejacode/main"
INSTALL_DIR="${DEJACODE_HOME:-$HOME/.dejacode}"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/dejacode"

# ── Output helpers ────────────────────────────────────────────────────────────
BOLD='\033[1m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}→${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
die()     { echo -e "${RED}✗${NC} $1" >&2; exit 1; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v docker &>/dev/null || die "Docker is required. See https://docs.docker.com/get-docker/"
docker info &>/dev/null       || die "Docker daemon is not running. Please start Docker first."
command -v curl &>/dev/null   || die "curl is required."

# ── Installation directory ────────────────────────────────────────────────────
info "Installing DejaCode in ${BOLD}$INSTALL_DIR${NC}"
mkdir -p "$INSTALL_DIR/data/postgresql"
cd "$INSTALL_DIR"

# ── Download files ────────────────────────────────────────────────────────────
info "Downloading compose.yml"
curl -sSL "$REPO/compose.yml" -o compose.yml

info "Downloading database seed data"
curl -sSL "$REPO/data/postgresql/initdb.sql.gz" -o data/postgresql/initdb.sql.gz

info "Downloading docker.env"
curl -sSL "$REPO/docker.env" -o docker.env

# ── Generate .env with a secure secret key ────────────────────────────────────
info "Generating .env"
# Read enough bytes from urandom so tr has enough after filtering, then cut to 50 chars.
# Avoids SIGPIPE/pipefail issues by not reading from an infinite stream.
SECRET_KEY=$(dd if=/dev/urandom bs=512 count=1 2>/dev/null \
    | LC_ALL=C tr -dc 'A-Za-z0-9!@#%^&*(-_=+)' \
    | cut -c1-50)
printf 'SECRET_KEY=%s\nALLOWED_HOSTS=localhost\nCSRF_TRUSTED_ORIGINS=http://localhost\n' \
    "$SECRET_KEY" > .env

# ── Install wrapper command ───────────────────────────────────────────────────
info "Installing dejacode command to $WRAPPER"
mkdir -p "$BIN_DIR"
# Write the wrapper using printf to avoid heredoc stdin conflicts when piped via curl | bash.
printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -eu' \
    "INSTALL_DIR=\"$INSTALL_DIR\"" \
    'case "${1:-}" in' \
    '    uninstall)' \
    '        printf "This will permanently delete all DejaCode data. Type '\''yes'\'' to confirm: "' \
    '        read -r CONFIRM' \
    '        [ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 1; }' \
    '        docker compose --project-directory "$INSTALL_DIR" down -v --remove-orphans 2>/dev/null || true' \
    '        rm -rf "$INSTALL_DIR"' \
    '        rm -f "$0"' \
    '        echo "DejaCode has been uninstalled."' \
    '        ;;' \
    '    *)' \
    '        cd "$INSTALL_DIR" && exec docker compose "$@"' \
    '        ;;' \
    'esac' \
    > "$WRAPPER"
chmod +x "$WRAPPER"

# ── Add ~/.local/bin to PATH if needed ───────────────────────────────────────
add_to_path() {
    local rc="$1"
    [ -f "$rc" ] || return
    grep -q '\.local/bin' "$rc" && return
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
    info "Added ~/.local/bin to PATH in $rc"
}

if [[ "$OSTYPE" == "darwin"* ]]; then
    add_to_path "$HOME/.zshrc"
else
    add_to_path "$HOME/.bashrc"
    add_to_path "$HOME/.profile"
fi

# ── Start services ────────────────────────────────────────────────────────────
info "Starting DejaCode"
docker compose up -d

# ── Wait for web to respond ───────────────────────────────────────────────────
info "Waiting for DejaCode to be ready"
RETRIES=40
until curl -fsS --max-time 5 http://localhost/ -o /dev/null 2>/dev/null; do
    RETRIES=$((RETRIES - 1))
    [ $RETRIES -eq 0 ] && die "Timed out waiting for DejaCode to start. Run: dejacode logs"
    echo -n "."
    sleep 3
done
echo ""

# ── Done ──────────────────────────────────────────────────────────────────────
success "DejaCode is running at ${BOLD}http://localhost${NC}"
echo ""
echo "  Create your admin user:  dejacode exec web ./manage.py createsuperuser"
echo "  Stop:                    dejacode down"
echo "  Logs:                    dejacode logs -f"
echo ""
echo "  Reload your shell or run: source ~/.zshrc (or ~/.bashrc)"
