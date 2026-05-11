// Transporter.js — warp entities or the player to specified world coords,
// with optional auto-restore after a roundtrip; drop the player from above
// with the off-map prep needed to bypass the engine's grounded snap.
//
// Mechanism: the placement primitive is oCEntity::setPosition at vtable
// slot +0x50 (RVA 0x6ca7f0) — writes the entity's position field at
// +0x324 and broadcasts to subscribers (renderer, camera, minimap).
// For arbitrary entities the engine resets the transform per frame, so
// warpEntity re-issues setPosition on a 500ms tick interval. The player
// has its own movement controller that respects a single setPosition
// without ticking, so warpPlayer is one-shot.
//
// Drop semantics: setPosition on a grounded player snaps the destination
// to the nearest walkable surface — Y is effectively ignored. To drop
// the player from above, a prior setPosition to off-map coords clears
// the grounded state (no walkable surface nearby), and a subsequent
// in-map setPosition then respects Y and gravity carries the player
// down. Both writes happen in the same JS turn; the engine processes
// them in order. Empirically observed Y ceiling for accepted drops:
// absolute Y ≤ 50; higher values re-engage the snap.
//
// Caveat — invisible-anchor entities:
//   Some entries in the encyclopedia (e.g. "[Entity spawner] NoModel",
//   "[Entity spawner] Enemy Camp") are spawn-anchor entities with no
//   visible model attached. warpEntity will write their position field
//   silently — nothing visible moves. To visit those anchor positions,
//   warp the player there with warpPlayer instead.
//
// Caveat — game-progression entities:
//   "[Entity spawner] NoModel+2Cpnt" is the chapter hourglass — drives
//   the boss-timer "leave-arena flips it" mechanic and the early-boss-
//   kill reward chain. Moving it is not blocked, but understand the
//   side effects before you do.
//
// Depends on:
//   - RW.Player (hub helper — call RW.Player.refresh() first)
//   - RW.Entity (hub helper)
//
// REPL surface (after loadPower("Transporter")):
//   Transporter.warpEntity(name, x, y, z, roundtrip?): void
//   Transporter.warpPlayer(x, y, z, roundtrip?): void
//   Transporter.warpPlayer(point, roundtrip?): void           overload
//   Transporter.dropPlayer(x, y, z, height?): void
//   Transporter.dropPlayer(point, height?): void              overload
//   Transporter.rotateEntity(name, yawDegrees, roundtrip?): void
//   Transporter.rotatePlayer(yawDegrees): void
//   Transporter.scaleEntity(name, s, roundtrip?): void
//   Transporter.scaleEntity(name, sx, sy, sz, roundtrip?): void  overload
//   Transporter.scalePlayer(s): void
//   Transporter.scalePlayer(sx, sy, sz): void                 overload
//   Transporter.expr_dropPlayerHard(x, y, z): void            experimental
//   Transporter.expr_dropPlayerHard(point): void              overload
//   Transporter.clear(): void

(function () {
    var version = "0.7.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Transporter] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    var POS_OFFSET        = 0x324;
    var ROT_OFFSET        = 0x308;
    var SCALE_OFFSET      = 0x318;
    var SET_POS_VT_SLOT   = 0x50;
    var SET_ROT_VT_SLOT   = 0x60;
    var SET_SCALE_VT_SLOT = 0x70;
    var TICK_MS           = 500;

    // Drop semantics — see file header.
    var DROP_HEIGHT_DEFAULT = 20;
    var DROP_Y_CEILING      = 50;
    var OFFMAP_PREP_X       = -410;
    var OFFMAP_PREP_Y       = 2;
    var OFFMAP_PREP_Z       = 0;

    if (!RW.Transporter) RW.Transporter = {};
    var Transporter = RW.Transporter;

    if (Transporter._timers && Transporter._timers.length) {
        Transporter._timers.forEach(function (id) {
            try { clearInterval(id); } catch (e) {}
            try { clearTimeout(id);  } catch (e) {}
        });
    }
    Transporter._timers = [];
    Transporter._entityTicks = Transporter._entityTicks || {};

    function clearEntityTick(key) {
        var t = Transporter._entityTicks[key];
        if (t !== undefined) {
            try { clearInterval(t); } catch (e) {}
            delete Transporter._entityTicks[key];
        }
    }

    function setEntityTick(key, place) {
        clearEntityTick(key);
        var tick = setInterval(place, TICK_MS);
        Transporter._entityTicks[key] = tick;
        Transporter._timers.push(tick);
        return tick;
    }

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p)    { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v)   { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }

    function setPosFor(ent) {
        var vt = ent.readPointer();
        return new NativeFunction(vt.add(SET_POS_VT_SLOT).readPointer(),
                                  'void', ['pointer', 'pointer']);
    }

    function setScaleFor(ent) {
        var vt = ent.readPointer();
        return new NativeFunction(vt.add(SET_SCALE_VT_SLOT).readPointer(),
                                  'void', ['pointer', 'pointer']);
    }

    function setRotFor(ent) {
        var vt = ent.readPointer();
        return new NativeFunction(vt.add(SET_ROT_VT_SLOT).readPointer(),
                                  'void', ['pointer', 'pointer']);
    }

    function yawDegToQuat(degrees) {
        var rad = degrees * Math.PI / 180;
        var half = rad / 2;
        return [0, Math.sin(half), 0, Math.cos(half)];  // x, y, z, w
    }

    // Internal — write the player's position bytes. Caller handles logging
    // and roundtrip scheduling.
    function writePlayerPos(x, y, z) {
        var player = RW.Player.entity;
        var setPos = setPosFor(player);
        var buf = Memory.alloc(12);
        buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
        setPos(player, buf);
    }

    // Normalize (a, b, c, d) → {x, y, z, tail} where tail is the trailing
    // optional arg (roundtrip for warpPlayer, height for dropPlayer).
    // Accepts (x, y, z, tail?) or ({x,y,z}, tail?).
    function normalizePointArgs(a, b, c, d) {
        if (typeof a === 'object' && a !== null) {
            return { x: a.x, y: a.y, z: a.z, tail: b };
        }
        return { x: a, y: b, z: c, tail: d };
    }

    function validXyz(p) {
        return typeof p.x === 'number' && typeof p.y === 'number' && typeof p.z === 'number';
    }

    /*
     * ----------------------------------------------------------------
     * Transporter.warpEntity(name: string, x: number, y: number, z: number, roundtrip?: number): void
     *
     * Move the named entity to (x, y, z). If roundtrip is provided
     * (seconds), the entity is restored to its original position after
     * that interval; otherwise it stays at the new position.
     *
     * Name is a case-insensitive substring match against RW.Entity
     * (e.g., "cauldron" → "[Entity spawner] Cauldron").
     *
     * Caveats:
     *   - Invisible-anchor entities (camps, NoModel) move silently —
     *     nothing visible relocates. Use warpPlayer to visit them.
     *   - The chapter hourglass (NoModel+2Cpnt) drives the boss-timer
     *     leave-arena flip and the early-boss-reward chain — moving
     *     it has progression side effects, but the call is not blocked.
     *
     * Result:
     *   On success the entity visibly relocates (if it has a renderer),
     *   tick-locked at the new position. If roundtrip given, restores
     *   to its captured original after that many seconds.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Resolves name via RW.Entity.find. Reads the oCEntity at
     *   settings+0x48, calls vtable[+0x50] (RVA 0x6ca7f0 setPosition)
     *   on a 500ms setInterval (defeats per-frame transform reset).
     *   On roundtrip expiry clears the interval and calls setPosition
     *   with the captured original position.
     */
    Transporter.warpEntity = function (name, x, y, z, roundtrip) {
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[Transporter.warpEntity] RW.Entity missing");
            return;
        }
        var hit = RW.Entity.find(name);
        if (!hit) { console.log("[Transporter.warpEntity] no match for \"" + name + "\""); return; }
        if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') {
            console.log("[Transporter.warpEntity] x, y, z must be numbers");
            return;
        }

        var origPos = vec3(hit.entity.add(POS_OFFSET));
        var setPos = setPosFor(hit.entity);
        var buf = Memory.alloc(12);

        function place() {
            buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
            setPos(hit.entity, buf);
        }
        place();
        var roundtripStr = (typeof roundtrip === 'number') ? " (roundtrip " + roundtrip + "s)" : " (no auto-restore)";
        console.log("[Transporter.warpEntity] " + hit.name + " -> " + v3str([x,y,z]) + roundtripStr);

        var key = "warp:" + hit.entity.toString();
        setEntityTick(key, place);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                clearEntityTick(key);
                buf.writeFloat(origPos[0]); buf.add(4).writeFloat(origPos[1]); buf.add(8).writeFloat(origPos[2]);
                setPos(hit.entity, buf);
                console.log("[Transporter.warpEntity] " + hit.name + " restored to " + v3str(origPos));
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.warpPlayer(x: number, y: number, z: number, roundtrip?: number): void
     * Transporter.warpPlayer(point: {x,y,z}, roundtrip?: number): void
     *
     * Warp the player to (x, y, z). If roundtrip is provided (seconds),
     * the player is returned to their original position after that
     * interval; otherwise they stay at the destination.
     *
     * Accepts either explicit (x, y, z, roundtrip?) or a point object
     * — pipe Map outputs directly:
     *   Transporter.warpPlayer(Map.center())
     *   Transporter.warpPlayer(Map.randomPoint(), 5)
     *
     * Caveats:
     *   - The engine's grounded-state snap may reposition the player
     *     to the nearest walkable surface. To drop from above (player
     *     falls), use Transporter.dropPlayer instead.
     *   - Warping into an active enemy camp will get the player killed
     *     — keep roundtrips short for combat-zone warps.
     *
     * Result:
     *   Player visibly snaps to the destination on the next frame.
     *   With roundtrip, snaps back to the captured original after that
     *   many seconds.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads RW.Player.entity, captures original position from
     *   player+0x324, calls vtable[+0x50] (RVA 0x6ca7f0 setPosition)
     *   with the destination. Schedules a single setPosition with the
     *   original position after roundtrip seconds — no tick loop
     *   needed (player movement controller respects a one-shot write).
     */
    Transporter.warpPlayer = function (a, b, c, d) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter.warpPlayer] RW.Player not captured — try RW.Player.refresh() and play one frame");
            return;
        }
        var args = normalizePointArgs(a, b, c, d);
        if (!validXyz(args)) {
            console.log("[Transporter.warpPlayer] need (x, y, z) or {x,y,z} — got " + JSON.stringify(args));
            return;
        }
        var roundtrip = args.tail;
        var player = RW.Player.entity;
        var origPos = vec3(player.add(POS_OFFSET));
        var setPos = setPosFor(player);
        var buf = Memory.alloc(12);

        buf.writeFloat(args.x); buf.add(4).writeFloat(args.y); buf.add(8).writeFloat(args.z);
        setPos(player, buf);
        var roundtripStr = (typeof roundtrip === 'number') ? " (return in " + roundtrip + "s)" : " (no auto-return)";
        console.log("[Transporter.warpPlayer] player -> " + v3str([args.x, args.y, args.z]) + roundtripStr);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                buf.writeFloat(origPos[0]); buf.add(4).writeFloat(origPos[1]); buf.add(8).writeFloat(origPos[2]);
                setPos(player, buf);
                console.log("[Transporter.warpPlayer] player returned to " + v3str(origPos));
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.dropPlayer(x: number, y: number, z: number, height?: number): void
     * Transporter.dropPlayer(point: {x,y,z}, height?: number): void
     *
     * Drop the player from above onto (x, z). The player free-falls
     * from absolute Y = (y + height) down to whatever surface lies
     * below (X, Z). Default height is 20; absolute target Y is clamped
     * to 50 (the empirical engine ceiling for accepted drop altitudes —
     * higher values re-engage the grounded snap).
     *
     * Pipes from Map:
     *   Transporter.dropPlayer(Map.center())
     *   Transporter.dropPlayer(Map.center(), 50)
     *   Transporter.dropPlayer(Map.randomPoint(50))
     *
     * Result:
     *   Player visibly falls from the chosen altitude and lands on
     *   terrain (or whatever non-walkable prop intercepts the fall).
     *
     * Caveats:
     *   - No roundtrip variant. Use warpPlayer with roundtrip if you
     *     need return-to-origin semantics.
     *   - Drop targets at landmarks (cauldron, hourglass, safe zone,
     *     etc.) re-engage the snap on landing — player lands ON the
     *     landmark surface. Drops onto raw terrain land normally.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Two stack-written setPosition calls in the same JS turn:
     *   1. Off-map prep at (-410, 2, 0) — outside the chapter's xMin
     *      bound, no walkable surface nearby, clears the grounded flag.
     *   2. In-map target at (x, min(y + height, 50), z) — controller
     *      now respects Y; gravity carries the player down.
     *   The engine processes both writes in order; the off-map state
     *   is never visible to the user because the second write replaces
     *   the position before any frame renders.
     */
    Transporter.dropPlayer = function (a, b, c, d) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter.dropPlayer] RW.Player not captured — try RW.Player.refresh() and play one frame");
            return;
        }
        var args = normalizePointArgs(a, b, c, d);
        if (!validXyz(args)) {
            console.log("[Transporter.dropPlayer] need (x, y, z) or {x,y,z} — got " + JSON.stringify(args));
            return;
        }
        var height = (typeof args.tail === 'number') ? args.tail : DROP_HEIGHT_DEFAULT;
        if (height < 0) height = 0;
        var targetY = args.y + height;
        var clamped = false;
        if (targetY > DROP_Y_CEILING) {
            targetY = DROP_Y_CEILING;
            clamped = true;
        }

        writePlayerPos(OFFMAP_PREP_X, OFFMAP_PREP_Y, OFFMAP_PREP_Z);
        writePlayerPos(args.x, targetY, args.z);

        console.log("[Transporter.dropPlayer] player -> " + v3str([args.x, targetY, args.z]) +
                    " (height=" + height + (clamped ? ", clamped to Y≤" + DROP_Y_CEILING : "") + ")");
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.rotateEntity(name: string, yawDegrees: number, roundtrip?: number): void
     *
     * Rotate a named entity around its vertical (Y) axis by yawDegrees.
     * 0 = neutral facing, 90 = quarter turn, 180 = facing opposite,
     * 360 = full revolution. Negative values rotate the other way.
     *
     * If roundtrip given (seconds), restored to original rotation
     * after that interval.
     *
     * Caveats:
     *   - Engine may reset non-player entity transforms per frame;
     *     rotation is re-applied on a 500ms tick.
     *   - Quaternion convention assumed xyzw with +Y up. If the entity
     *     visibly tilts instead of yawing, the engine may use a
     *     different axis convention — fall back to setRotation with a
     *     hand-tuned 4-tuple.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Converts yaw to a unit quaternion (qx=0, qy=sin(rad/2), qz=0,
     *   qw=cos(rad/2)) and writes via vt[+0x60] (RVA 0x6ca8d0). Engine
     *   stores it at +0x308..+0x314.
     */
    Transporter.rotateEntity = function (name, yawDegrees, roundtrip) {
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[Transporter.rotateEntity] RW.Entity missing");
            return;
        }
        var hit = RW.Entity.find(name);
        if (!hit) { console.log("[Transporter.rotateEntity] no match for \"" + name + "\""); return; }
        if (typeof yawDegrees !== 'number') {
            console.log("[Transporter.rotateEntity] need (name, yawDegrees, roundtrip?)");
            return;
        }

        var q = yawDegToQuat(yawDegrees);
        var origRot = [
            hit.entity.add(ROT_OFFSET     ).readFloat(),
            hit.entity.add(ROT_OFFSET + 4 ).readFloat(),
            hit.entity.add(ROT_OFFSET + 8 ).readFloat(),
            hit.entity.add(ROT_OFFSET + 12).readFloat(),
        ];
        var setRot = setRotFor(hit.entity);
        var buf = Memory.alloc(16);

        function place() {
            buf.writeFloat(q[0]);
            buf.add(4).writeFloat(q[1]);
            buf.add(8).writeFloat(q[2]);
            buf.add(12).writeFloat(q[3]);
            setRot(hit.entity, buf);
        }
        place();
        var roundtripStr = (typeof roundtrip === 'number') ? " (roundtrip " + roundtrip + "s)" : " (no auto-restore)";
        console.log("[Transporter.rotateEntity] " + hit.name + " yaw=" + yawDegrees + "°" + roundtripStr);

        var key = "rotate:" + hit.entity.toString();
        setEntityTick(key, place);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                clearEntityTick(key);
                buf.writeFloat(origRot[0]);
                buf.add(4).writeFloat(origRot[1]);
                buf.add(8).writeFloat(origRot[2]);
                buf.add(12).writeFloat(origRot[3]);
                setRot(hit.entity, buf);
                console.log("[Transporter.rotateEntity] " + hit.name + " rotation restored");
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.rotatePlayer(yawDegrees: number): void
     *
     * Rotate the player around the vertical axis by yawDegrees. Like
     * scalePlayer, this is a one-shot write (no tick loop). Player
     * movement controller respects the rotation until the next input
     * that re-aims the character.
     *
     * Result: player visibly turns. Logs the new yaw.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Calls oCEntity::setRotation at vtable[+0x60] (RVA 0x6ca8d0)
     *   with a yaw-only quaternion. Same primitive as rotateEntity.
     */
    Transporter.rotatePlayer = function (yawDegrees) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter.rotatePlayer] RW.Player not captured — try RW.Player.refresh()");
            return;
        }
        if (typeof yawDegrees !== 'number') {
            console.log("[Transporter.rotatePlayer] need (yawDegrees)");
            return;
        }
        var q = yawDegToQuat(yawDegrees);
        var player = RW.Player.entity;
        var setRot = setRotFor(player);
        var buf = Memory.alloc(16);
        buf.writeFloat(q[0]);
        buf.add(4).writeFloat(q[1]);
        buf.add(8).writeFloat(q[2]);
        buf.add(12).writeFloat(q[3]);
        setRot(player, buf);
        console.log("[Transporter.rotatePlayer] yaw=" + yawDegrees + "°");
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.scaleEntity(name: string, sx: number, sy: number, sz: number, roundtrip?: number): void
     * Transporter.scaleEntity(name: string, s: number, roundtrip?: number): void
     *
     * Resize a named entity. Same name resolution as warpEntity (case-
     * insensitive substring match via RW.Entity.find). Single number
     * = uniform scale; three numbers = independent xyz.
     *
     * If roundtrip given (seconds), entity is restored to its captured
     * original scale after that interval.
     *
     * Caveats:
     *   - Engine may reset non-player entity transforms per frame
     *     (same reason warpEntity needs a tick loop). Scale is
     *     re-applied on a 500ms tick to defeat that.
     *   - Invisible-anchor entities (NoModel, Enemy Camp, etc.) — the
     *     scale field gets written but nothing visible changes because
     *     no model is attached.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   RW.Entity.find resolves to oCEntity. setScale at vt[+0x70]
     *   (RVA 0x6ca9e0) writes 3 floats at +0x318..+0x320, fires a
     *   500ms re-apply tick, optional roundtrip restores capture.
     */
    Transporter.scaleEntity = function (name, a, b, c, d) {
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[Transporter.scaleEntity] RW.Entity missing");
            return;
        }
        var hit = RW.Entity.find(name);
        if (!hit) { console.log("[Transporter.scaleEntity] no match for \"" + name + "\""); return; }

        var sx, sy, sz, roundtrip;
        if (typeof a === 'number' && (b === undefined || typeof b !== 'number') && c === undefined) {
            sx = sy = sz = a;
            roundtrip = b;
        } else if (typeof a === 'number' && typeof b === 'number' && c === undefined) {
            // (name, s, roundtrip)
            sx = sy = sz = a;
            roundtrip = b;
        } else if (typeof a === 'number' && typeof b === 'number' && typeof c === 'number') {
            sx = a; sy = b; sz = c;
            roundtrip = d;
        } else {
            console.log("[Transporter.scaleEntity] need (name, s, roundtrip?) or (name, sx, sy, sz, roundtrip?)");
            return;
        }

        var origScale = vec3(hit.entity.add(SCALE_OFFSET));
        var setScale = setScaleFor(hit.entity);
        var buf = Memory.alloc(12);

        function place() {
            buf.writeFloat(sx); buf.add(4).writeFloat(sy); buf.add(8).writeFloat(sz);
            setScale(hit.entity, buf);
        }
        place();
        var roundtripStr = (typeof roundtrip === 'number') ? " (roundtrip " + roundtrip + "s)" : " (no auto-restore)";
        console.log("[Transporter.scaleEntity] " + hit.name + " -> (" +
                    sx.toFixed(2) + "," + sy.toFixed(2) + "," + sz.toFixed(2) + ")" + roundtripStr);

        var key = "scale:" + hit.entity.toString();
        setEntityTick(key, place);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                clearEntityTick(key);
                buf.writeFloat(origScale[0]); buf.add(4).writeFloat(origScale[1]); buf.add(8).writeFloat(origScale[2]);
                setScale(hit.entity, buf);
                console.log("[Transporter.scaleEntity] " + hit.name + " restored to (" +
                            origScale[0].toFixed(2) + "," + origScale[1].toFixed(2) + "," + origScale[2].toFixed(2) + ")");
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.scalePlayer(s: number): void
     * Transporter.scalePlayer(sx: number, sy: number, sz: number): void
     *
     * Resize the player. One number = uniform scale on all three axes;
     * three numbers = independent xyz. Default game scale is 1.0; try
     * 0.5 for half size, 2.0 for double, etc.
     *
     * Result: player visibly resizes on the next render. Persists until
     * something else writes the scale field. Logs the new (sx, sy, sz).
     *
     * Caveats:
     *   - Extreme values may break collision / animation. Stay near 1.0
     *     to start.
     *   - Scale is on the entity, not the model — collision capsule and
     *     hitbox may or may not follow depending on which subsystems
     *     subscribed to the scale broadcast.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Calls oCEntity::setScale at vtable[+0x70] (RVA 0x6ca9e0) with
     *   3 floats at +0x318..+0x320. Sibling primitive to setPosition
     *   (+0x50) and setRotation (+0x60). Same dirty/broadcast plumbing
     *   but type code 2 (vs 0 for position, 1 for rotation).
     */
    Transporter.scalePlayer = function (a, b, c) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter.scalePlayer] RW.Player not captured — try RW.Player.refresh()");
            return;
        }
        var sx, sy, sz;
        if (typeof a === 'number' && b === undefined && c === undefined) {
            sx = sy = sz = a;
        } else if (typeof a === 'number' && typeof b === 'number' && typeof c === 'number') {
            sx = a; sy = b; sz = c;
        } else {
            console.log("[Transporter.scalePlayer] need (s) or (sx, sy, sz)");
            return;
        }
        var player = RW.Player.entity;
        var setScale = setScaleFor(player);
        var buf = Memory.alloc(12);
        buf.writeFloat(sx); buf.add(4).writeFloat(sy); buf.add(8).writeFloat(sz);
        setScale(player, buf);
        console.log("[Transporter.scalePlayer] player scale -> (" +
                    sx.toFixed(2) + "," + sy.toFixed(2) + "," + sz.toFixed(2) + ")");
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.expr_dropPlayerHard(x: number, y: number, z: number): void
     * Transporter.expr_dropPlayerHard(point: {x,y,z}): void
     *
     * Experimental. Writes the player's broadcast position field AND
     * the movement controller's internal "prev" and "target" position
     * triplets to (x, y, z) in one shot. If the controller's per-tick
     * loop is gated by (target != prev), this should suppress the snap
     * by leaving the diff at zero — the player stays at the requested
     * position (including high Y) without holding movement input.
     *
     * Result: player relocates to (x, y, z). Watch whether they hold
     * altitude or get pulled back — that tells us whether anything
     * upstream re-computes target each frame independently of our
     * write.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Player movement controller, decompiled from
     *   oCEntity_VelocityUpdate_loop (RVA 0x6cc??0): the loop fires
     *   setPosition(target) only when any axis of target differs from
     *   prev:
     *     prev   at entity+0x3d8..+0x3e0  (xyz floats, contiguous)
     *     target at entity+0x3e4..+0x3ec  (xyz floats, contiguous)
     *   We write prev = target = (x, y, z), then call setPosition to
     *   update the broadcast field at +0x324..+0x32c.
     */
    Transporter.expr_dropPlayerHard = function (a, b, c) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter.expr_dropPlayerHard] RW.Player not captured — try RW.Player.refresh()");
            return;
        }
        var args = normalizePointArgs(a, b, c);
        if (!validXyz(args)) {
            console.log("[Transporter.expr_dropPlayerHard] need (x, y, z) or {x,y,z} — got " + JSON.stringify(args));
            return;
        }
        var player = RW.Player.entity;

        player.add(0x3d8).writeFloat(args.x);
        player.add(0x3dc).writeFloat(args.y);
        player.add(0x3e0).writeFloat(args.z);
        player.add(0x3e4).writeFloat(args.x);
        player.add(0x3e8).writeFloat(args.y);
        player.add(0x3ec).writeFloat(args.z);

        writePlayerPos(args.x, args.y, args.z);

        console.log("[Transporter.expr_dropPlayerHard] player -> " + v3str([args.x, args.y, args.z]) +
                    " (prev/target/pos all written)");
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.clear(): void
     *
     * Cancel every active warpEntity tick interval and pending
     * roundtrip timer. Does NOT restore positions — entities and the
     * player stay wherever they were when clear() was called. Useful
     * for aborting in-flight roundtrips before a power reload.
     * ----------------------------------------------------------------
     */
    Transporter.clear = function () {
        Transporter._timers.forEach(function (id) {
            try { clearInterval(id); } catch (e) {}
            try { clearTimeout(id);  } catch (e) {}
        });
        Transporter._timers = [];
        console.log("[Transporter] all active operations cleared (no position restore)");
    };

    RW.registerMod("power:Transporter", version);
    console.log("[Transporter] " + version + " loaded.");
    console.log("[Transporter]   warpEntity(name, x, y, z, roundtrip?)");
    console.log("[Transporter]   warpPlayer(x, y, z, roundtrip?)  /  warpPlayer(point, roundtrip?)");
    console.log("[Transporter]   dropPlayer(x, y, z, height?)     /  dropPlayer(point, height?)");
    console.log("[Transporter]   rotateEntity(name, yawDeg, rt?)");
    console.log("[Transporter]   rotatePlayer(yawDeg)");
    console.log("[Transporter]   scaleEntity(name, s, rt?)        /  scaleEntity(name, sx, sy, sz, rt?)");
    console.log("[Transporter]   scalePlayer(s)                   /  scalePlayer(sx, sy, sz)");
    console.log("[Transporter]   expr_dropPlayerHard(x, y, z)     /  expr_dropPlayerHard(point)   [experimental]");
})();

// Top-level alias for REPL convenience
var Transporter = RW.Transporter;
