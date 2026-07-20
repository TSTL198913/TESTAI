import re
from typing import Any, Dict


def render_template(
    data: Any, lookup_dict: Dict[str, Any], strict: bool = False
) -> Any:
    """递归渲染模板，支持严格模式"""

    if isinstance(data, str):
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(m):
            var_name = m.group(1).strip()
            if var_name not in lookup_dict:
                if strict:
                    # 抛出原始 Key，由上层 DataProcessor 捕获并转化为 VariableMissingError
                    raise KeyError(var_name)
                return m.group(0)
            return str(lookup_dict[var_name])

        return pattern.sub(replacer, data)

    elif isinstance(data, dict):
        return {
            k: render_template(v, lookup_dict, strict=strict) for k, v in data.items()
        }
    elif isinstance(data, list):
        return [render_template(item, lookup_dict, strict=strict) for item in data]

    return data
