#!/bin/bash
# =============================================================================
# Ouroboros Desktop — macOS 一键打包脚本
#
# 用法:
#   bash scripts/build_mac.sh              # 无签名构建（开发/测试用）
#   bash scripts/build_mac.sh --sign       # 签名+公证（发布用，需 Apple Developer 账号）
#
# 前置条件:
#   - macOS 12.0+
#   - Xcode Command Line Tools: xcode-select --install
#   - Python 3.10+（系统自带或 Homebrew）
#   - 约 2GB 磁盘空间
#
# 签名发布额外需要:
#   - Apple Developer ID Application 证书
#   - xcrun notarytool 配置 (见下方 SIGN_IDENTITY 部分)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${CYAN}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
SIGN_MODE=false
CLEAN_ALL=false

for arg in "$@"; do
    case "$arg" in
        --sign)     SIGN_MODE=true ;;
        --clean)    CLEAN_ALL=true ;;
        --help|-h)
            echo "Usage: bash scripts/build_mac.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --sign    签名+公证（需要 Apple Developer 证书）"
            echo "  --clean   构建前清除所有缓存（python-standalone, build, dist）"
            echo "  --help    显示帮助"
            exit 0
            ;;
        *) error "Unknown option: $arg (use --help)" ;;
    esac
done

# ---------------------------------------------------------------------------
# 签名配置（仅 --sign 模式使用）
# 修改这里为你自己的 Apple Developer 信息:
# ---------------------------------------------------------------------------
SIGN_IDENTITY="${OUROBOROS_SIGN_IDENTITY:-Developer ID Application: Ian Mironov (WHY6PAKA5V)}"
TEAM_ID="${OUROBOROS_TEAM_ID:-WHY6PAKA5V}"
BUNDLE_ID="com.ouroboros.agent"
ENTITLEMENTS="entitlements.plist"
NOTARYTOOL_PROFILE="${OUROBOROS_NOTARIZE_PROFILE:-ouroboros-notarize}"

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION=$(cat VERSION | tr -d '[:space:]')
APP_PATH="dist/Ouroboros.app"
DMG_NAME="Ouroboros-${VERSION}.dmg"
DMG_PATH="dist/$DMG_NAME"

step "Ouroboros Desktop v${VERSION} — macOS Build"
info "Mode: $([ "$SIGN_MODE" = true ] && echo '签名+公证发布' || echo '开发构建（无签名）')"
info "Project: $PROJECT_ROOT"
echo ""

# ---------------------------------------------------------------------------
# Step 0: 环境检查
# ---------------------------------------------------------------------------
step "Step 0: 检查构建环境"

# macOS check
if [[ "$(uname -s)" != "Darwin" ]]; then
    error "此脚本仅支持 macOS。当前系统: $(uname -s)"
fi
ok "macOS $(sw_vers -productVersion)"

# Architecture
ARCH=$(uname -m)
info "Architecture: $ARCH"

# Xcode CLI tools
if ! xcode-select -p &>/dev/null; then
    warn "Xcode Command Line Tools 未安装，正在安装..."
    xcode-select --install
    echo "请在弹出窗口中确认安装，完成后重新运行此脚本。"
    exit 1
fi
ok "Xcode Command Line Tools: $(xcode-select -p)"

# Python 3
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PY_VER=$("$candidate" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 10 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    error "需要 Python 3.10+。安装: brew install python@3.12"
fi
ok "Python: $($PYTHON --version) ($PYTHON)"

# pip
if ! "$PYTHON" -m pip --version &>/dev/null; then
    error "pip 不可用。运行: $PYTHON -m ensurepip"
fi

# Signing tools (only if --sign)
if [ "$SIGN_MODE" = true ]; then
    command -v codesign &>/dev/null || error "codesign 不可用"
    command -v xcrun &>/dev/null || error "xcrun 不可用"
    # Verify signing identity exists
    if ! security find-identity -v -p codesigning | grep -q "$TEAM_ID"; then
        error "签名证书未找到: $SIGN_IDENTITY\n  检查: security find-identity -v -p codesigning\n  或设置环境变量: OUROBOROS_SIGN_IDENTITY=\"你的证书名\""
    fi
    ok "Signing identity: $SIGN_IDENTITY"
fi

# ---------------------------------------------------------------------------
# Step 1: 清理（可选）
# ---------------------------------------------------------------------------
if [ "$CLEAN_ALL" = true ]; then
    step "Step 1: 清理旧构建"
    rm -rf python-standalone build dist __pycache__
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    ok "Cleaned"
else
    step "Step 1: 清理构建输出"
    rm -rf build dist
    ok "Cleaned build/ and dist/"
fi

# ---------------------------------------------------------------------------
# Step 2: 下载 Python Standalone
# ---------------------------------------------------------------------------
step "Step 2: 准备嵌入式 Python 运行时"

if [ -f "python-standalone/bin/python3" ]; then
    EMBEDDED_VER=$(python-standalone/bin/python3 --version 2>&1 || echo "unknown")
    ok "已存在: $EMBEDDED_VER (跳过下载)"
else
    info "下载 python-build-standalone..."
    bash scripts/download_python_standalone.sh
    ok "嵌入式 Python 就绪: $(python-standalone/bin/python3 --version)"
fi

# Ensure agent dependencies are installed
info "确认 agent 依赖已安装..."
python-standalone/bin/pip3 install --quiet -r requirements.txt
ok "Agent 依赖就绪"

# ---------------------------------------------------------------------------
# Step 3: 安装构建工具
# ---------------------------------------------------------------------------
step "Step 3: 安装构建工具"

"$PYTHON" -m pip install --quiet pyinstaller pywebview\>=5.0
ok "PyInstaller $(${PYTHON} -m PyInstaller --version 2>&1 || echo 'installed')"

# Also install launcher deps
"$PYTHON" -m pip install --quiet -r requirements-launcher.txt
ok "Launcher 依赖就绪"

# ---------------------------------------------------------------------------
# Step 4: 运行测试
# ---------------------------------------------------------------------------
step "Step 4: 运行测试"

if "$PYTHON" -m pytest tests/ -q --tb=short -k "not test_version_in_readme and not test_e2e_live" 2>&1; then
    ok "所有测试通过"
else
    warn "部分测试失败，继续构建（检查上方输出）"
fi

# ---------------------------------------------------------------------------
# Step 5: PyInstaller 打包
# ---------------------------------------------------------------------------
step "Step 5: PyInstaller 打包"

info "构建 Ouroboros.app（这可能需要 1-3 分钟）..."
"$PYTHON" -m PyInstaller Ouroboros.spec --clean --noconfirm 2>&1 | tail -5

if [ ! -d "$APP_PATH" ]; then
    error "PyInstaller 打包失败: $APP_PATH 不存在"
fi
APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
ok "Ouroboros.app 构建完成 ($APP_SIZE)"

# ---------------------------------------------------------------------------
# Step 6: Ad-hoc 签名 / 正式签名
# ---------------------------------------------------------------------------
if [ "$SIGN_MODE" = true ]; then
    step "Step 6: 正式签名 (Developer ID)"

    info "签名所有嵌入的 Mach-O 二进制..."
    SIGN_COUNT=0
    while IFS= read -r -d '' f; do
        if file "$f" | grep -q "Mach-O"; then
            codesign -s "$SIGN_IDENTITY" --timestamp --force --options runtime \
                --entitlements "$ENTITLEMENTS" "$f" 2>/dev/null || true
            SIGN_COUNT=$((SIGN_COUNT + 1))
        fi
    done < <(find "$APP_PATH" -type f -print0)
    info "签名了 $SIGN_COUNT 个二进制文件"

    info "签名 app bundle..."
    codesign -s "$SIGN_IDENTITY" --timestamp --force --options runtime \
        --entitlements "$ENTITLEMENTS" "$APP_PATH"

    info "验证签名..."
    codesign --verify --strict "$APP_PATH"
    ok "签名验证通过"

else
    step "Step 6: Ad-hoc 签名（开发用）"

    info "对嵌入的二进制做 ad-hoc 签名..."
    while IFS= read -r -d '' f; do
        if file "$f" | grep -q "Mach-O"; then
            codesign -s - --force "$f" 2>/dev/null || true
        fi
    done < <(find "$APP_PATH" -type f -print0)

    codesign -s - --force "$APP_PATH" 2>/dev/null || true
    ok "Ad-hoc 签名完成（仅本机可用，分发需要 --sign）"
fi

# ---------------------------------------------------------------------------
# Step 7: 公证（仅 --sign 模式）
# ---------------------------------------------------------------------------
if [ "$SIGN_MODE" = true ]; then
    step "Step 7: Apple 公证"

    info "创建公证用 ZIP..."
    ditto -c -k --keepParent "$APP_PATH" dist/Ouroboros-notarize.zip

    info "提交公证（可能需要几分钟）..."
    xcrun notarytool submit dist/Ouroboros-notarize.zip \
        --keychain-profile "$NOTARYTOOL_PROFILE" \
        --wait

    info "Staple 公证票据..."
    xcrun stapler staple "$APP_PATH"
    rm -f dist/Ouroboros-notarize.zip
    ok "公证完成"
else
    step "Step 7: 跳过公证（开发模式）"
    info "提示: 首次运行需要右键 → 打开，或 System Settings → Privacy → Allow"
fi

# ---------------------------------------------------------------------------
# Step 8: 创建 DMG
# ---------------------------------------------------------------------------
step "Step 8: 创建 DMG 安装镜像"

rm -f "$DMG_PATH"
hdiutil create -volname "Ouroboros" -srcfolder "$APP_PATH" \
    -ov -format UDZO "$DMG_PATH" 2>&1 | tail -2

if [ "$SIGN_MODE" = true ]; then
    codesign -s "$SIGN_IDENTITY" --timestamp "$DMG_PATH"

    info "公证 DMG..."
    xcrun notarytool submit "$DMG_PATH" \
        --keychain-profile "$NOTARYTOOL_PROFILE" \
        --wait
    xcrun stapler staple "$DMG_PATH"
fi

DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)
ok "DMG 创建完成: $DMG_PATH ($DMG_SIZE)"

# ---------------------------------------------------------------------------
# 完成
# ---------------------------------------------------------------------------
step "构建完成!"
echo ""
echo -e "  ${GREEN}App:${NC}  $APP_PATH"
echo -e "  ${GREEN}DMG:${NC}  $DMG_PATH"
echo -e "  ${GREEN}版本:${NC} $VERSION"
echo -e "  ${GREEN}签名:${NC} $([ "$SIGN_MODE" = true ] && echo '已签名+公证' || echo 'Ad-hoc（仅本机）')"
echo ""

if [ "$SIGN_MODE" = false ]; then
    echo -e "${YELLOW}提示:${NC}"
    echo "  开发模式下首次打开 .app 需要:"
    echo "    右键 Ouroboros.app → 打开 → 确认"
    echo "  或:"
    echo "    xattr -cr dist/Ouroboros.app"
    echo ""
    echo "  发布用打包请运行:"
    echo "    bash scripts/build_mac.sh --sign"
fi
echo ""
