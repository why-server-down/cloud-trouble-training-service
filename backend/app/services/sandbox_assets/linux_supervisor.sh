#!/bin/sh
# Linux 샌드박스의 메인 프로세스.
#
# 왜 필요한가: Kubernetes exec 으로 띄운 백그라운드 프로세스는 exec 세션이 끝나면
# containerd 가 프로세스 그룹째 정리한다(BE-17 실측). 그래서 장애 워크로드를 exec 으로
# 직접 띄울 수 없다. 이 스크립트가 Pod 의 PID 1 로 살아 있으면서 신호 파일을 보고
# 워크로드를 대신 띄운다.
#
# 사용자가 워크로드를 종료하면 그대로 둔다. 다시 띄우면 복구가 불가능해진다.
set -eu

WORKDIR="${AFTERFAIL_WORKDIR:-/tmp/afterfail}"
SIGNALS="$WORKDIR/.signals"
POLL="${AFTERFAIL_POLL_SECONDS:-2}"

mkdir -p "$WORKDIR" "$SIGNALS"

# 워크로드는 이름으로 식별한다. 명령 정책이 afterfail- 로 시작하는 프로세스만
# 신호 대상으로 허용하므로, 바이너리를 그 이름으로 복사해 실행한다.
# 워크로드는 이름으로 식별한다. 명령 정책이 afterfail- 로 시작하는 대상만 신호를
# 허용하므로, 그 이름을 가진 실행 스크립트를 만들어 띄운다.
#
# 바이너리를 복사해 이름을 바꾸지 않는 이유: 이 이미지의 명령은 전부 busybox
# 심볼릭 링크이고 busybox 는 argv[0] 으로 applet 을 고른다. 이름을 바꾸면
# "applet not found" 로 실행되지 않는다(BE-17 실측).
#
# 스크립트 안에서 exec 을 쓰지 않는다. exec 하면 프로세스가 대상 명령으로 교체돼
# 명령줄에서 afterfail- 이름이 사라지고 사용자가 pkill -f 로 찾을 수 없다.
prepare_worker() {
    _name="$1"
    _body="$2"
    printf '#!/bin/sh\n%s\n' "$_body" > "$WORKDIR/$_name"
    chmod +x "$WORKDIR/$_name"
}

start_process_flood() {
    _count="${1:-120}"
    prepare_worker afterfail-worker 'sleep 86400'
    _i=0
    while [ "$_i" -lt "$_count" ]; do
        "$WORKDIR/afterfail-worker" >/dev/null 2>&1 &
        _i=$((_i + 1))
    done
}

start_cpu_saturation() {
    # CPU 를 계속 태우는 워크로드. 컨테이너 CPU 상한 안에서만 돌아 노드에 영향이 없다.
    prepare_worker afterfail-cpuburn 'while :; do :; done'
    _count="${1:-2}"
    _i=0
    while [ "$_i" -lt "$_count" ]; do
        "$WORKDIR/afterfail-cpuburn" >/dev/null 2>&1 &
        _i=$((_i + 1))
    done
}

start_disk_pressure() {
    _mb="${1:-56}"
    dd if=/dev/zero of="$WORKDIR/afterfail-fill.dat" bs=1M count="$_mb" >/dev/null 2>&1 || true
}

# 신호 파일이 새로 생겼을 때 한 번만 실행한다.
# 이미 처리한 신호는 .done 으로 표시해, 사용자가 워크로드를 정리한 뒤
# 다시 살아나지 않게 한다.
handle_signal() {
    _name="$1"
    _sig="$SIGNALS/$_name"
    [ -f "$_sig" ] || return 0
    [ -f "$_sig.done" ] && return 0

    _arg="$(cat "$_sig" 2>/dev/null || true)"
    case "$_name" in
        process_flood) start_process_flood "$_arg" ;;
        cpu_saturation) start_cpu_saturation "$_arg" ;;
        disk_pressure) start_disk_pressure "$_arg" ;;
    esac
    : > "$_sig.done"
}

trap 'exit 0' TERM INT

while true; do
    handle_signal process_flood
    handle_signal cpu_saturation
    handle_signal disk_pressure
    sleep "$POLL"
done
