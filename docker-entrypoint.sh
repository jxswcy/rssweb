#!/bin/sh
# 以 root 身份修复 /data 权限后切换到 appuser 运行
chown -R appuser:appuser /data 2>/dev/null || true
exec gosu appuser "$@"
