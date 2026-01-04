# Security & Performance Configuration

> **Applied**: 2026-01-04 | **Version**: Howdy Optimized

## Current Setup

All anti-spoofing features enabled with high security level:

```ini
[security]
liveness_check = true
security_level = high
active_challenge = true
frequency_analysis = true
temporal_analysis = true

[daemon]
enabled = true

[video]
certainty = 4.0
save_failed = true
end_report = true
```

## What's Protected Against

- 📷 Photos (frequency analysis detects screen moiré patterns)
- 🎥 Video replays (temporal consistency checks)
- 🎭 Masks (passive liveness + active challenges)
- 📱 Phone/monitor displays (combined frequency + temporal analysis)

## Quick Reference

**Test recognition:**
```bash
howdy test
```

**Add model variants:**
```bash
howdy add  # with glasses
howdy add  # different lighting
```

**Check daemon status:**
```bash
ps aux | grep model_daemon
```

**View failed attempts:**
```bash
ls -lh /var/log/howdy/snapshots/
```

## Performance Impact

| Metric | With Daemon | Without Daemon |
|--------|-------------|----------------|
| Cold start | ~50-100ms | ~1000-2000ms |
| Subsequent | ~10-30ms | ~1000-2000ms |
| CPU load | Minimal | Peak on each auth |

## Active Challenge Behavior

When confidence is low, you'll be prompted to:
- Blink
- Turn head left/right  
- Nod up/down

This is **normal** - just perform the action. Adds 1-3s but significantly increases security.

## Troubleshooting

**Too slow?**
- Verify daemon running
- Lower `security_level` to `medium`

**Too many false rejections?**
- Decrease `certainty` to 3.0-3.5
- Add more model variants

**Not working with glasses?**
- Add dedicated model: `howdy add`

---

## About

Based on [Howdy](https://github.com/boltgolt/howdy) - Windows Hello™ style face authentication for Linux.

**This Fork**: https://github.com/WonderMr/howdy  
**Original**: https://github.com/boltgolt/howdy
