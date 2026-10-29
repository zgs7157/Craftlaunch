# -*- coding: utf-8 -*-
"""版本继承（inheritsFrom）展开：Fabric / Forge / NeoForge / OptiFine 等加载器版本
只包含自身差异，游戏本体 jar、参数、资源等要继承自父版本（如 1.21.1）。

用法：
  loader = lambda vid: <该 vid 的原始版本 JSON（官方或本地）>
  merged = expand_version_json(vid, loader)
"""
import copy


def expand_version_json(vid, loader):
    """展开继承链，返回合并后的版本 JSON。

    - libraries：父级在前、子级在后，同名去重（子级覆盖）
    - arguments.jvm / game：父级 + 子级拼接
    - mainClass / downloads / assetIndex / logging / javaVersion / minecraftArguments：
      子级有就用子级，否则用父级
    - 保留 inheritsFrom 字段（供定位客户端 jar / 显示用）
    """
    seen = set()

    def walk(v):
        if v in seen:
            return {}
        seen.add(v)
        vj = loader(v) or {}
        parent_id = vj.get("inheritsFrom")
        merged = walk(parent_id) if parent_id else {}

        # libraries：父级 + 子级，同名去重（子级覆盖）
        libs = [copy.deepcopy(l) for l in merged.get("libraries") or [] if isinstance(l, dict)]
        names = {l.get("name") for l in libs if l.get("name")}
        for l in vj.get("libraries") or []:
            if not isinstance(l, dict):
                continue
            if l.get("name") in names:
                libs = [x for x in libs if x.get("name") != l.get("name")]
            libs.append(copy.deepcopy(l))
        merged["libraries"] = libs

        # arguments：父级 + 子级拼接（子级附加在后）
        args = dict(merged.get("arguments") or {})
        args["jvm"] = list(args.get("jvm") or []) + list((vj.get("arguments") or {}).get("jvm") or [])
        args["game"] = list(args.get("game") or []) + list((vj.get("arguments") or {}).get("game") or [])
        merged["arguments"] = args

        # 标量字段：子级优先（覆盖父级），子级缺失时保留父级值
        for key in ("mainClass", "downloads", "assetIndex", "logging",
                    "javaVersion", "minecraftArguments", "type"):
            if key in vj:
                merged[key] = copy.deepcopy(vj[key])

        merged["id"] = v
        if parent_id:
            merged["inheritsFrom"] = parent_id
        return merged

    return walk(vid)
