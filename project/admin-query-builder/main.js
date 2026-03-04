const AVAILABLE_FIELDS = [
  "user.email",
  "user.username",
  "user.first_name",
  "user.last_name",
  "user.is_active",
  "profile.age",
  "profile.country",
  "order.total",
  "order.status",
  "order.created_at",
  "product.name",
  "product.category",
  "product.price",
];

const DJANGO_LOOKUPS = [
  "exact",
  "iexact",
  "contains",
  "icontains",
  "gt",
  "gte",
  "lt",
  "lte",
  "in",
  "isnull",
  "startswith",
  "istartswith",
  "endswith",
  "iendswith",
  "range",
  "date",
  "year",
  "month",
];

const DJANGO_LOOKUP_SET = new Set(DJANGO_LOOKUPS);

const FRONTEND_OPERATOR_LOOKUPS = {
  equals: "exact",
  not_equals: "exact",
  contains: "contains",
  not_contains: "contains",
  greater_than: "gt",
  less_than: "lt",
  in: "in",
  not_in: "in",
};

const OPERATOR_ALIASES = {
  eq: "exact",
  ne: "exact",
  starts_with: "startswith",
  istarts_with: "istartswith",
  i_starts_with: "istartswith",
  ends_with: "endswith",
  iends_with: "iendswith",
  i_ends_with: "iendswith",
};

const LOOKUP_LABELS = {
  eq: "Equals",
  ne: "Not Equals",
  exact: "Exact Match",
  iexact: "Exact Match (Case-Insensitive)",
  contains: "Contains",
  icontains: "Contains (Case-Insensitive)",
  gt: "Greater Than",
  gte: "Greater Than or Equal",
  lt: "Less Than",
  lte: "Less Than or Equal",
  in: "In List",
  isnull: "Is Null",
  startswith: "Starts With",
  istartswith: "Starts With (Case-Insensitive)",
  endswith: "Ends With",
  iendswith: "Ends With (Case-Insensitive)",
  range: "In Range",
  date: "Date",
  year: "Year",
  month: "Month",
};

function dunderOperatorLabel(lookup) {
  const human = LOOKUP_LABELS[lookup] || lookup;
  return human;
}

const OPERATOR_OPTIONS = [
  { value: "equals", label: "Equals" },
  { value: "not_equals", label: "Not Equals" },
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Not Contains" },
  { value: "greater_than", label: "Greater Than" },
  { value: "less_than", label: "Less Than" },
  { value: "in", label: "In" },
  { value: "not_in", label: "Not In" },
  { value: "__eq", label: dunderOperatorLabel("eq") },
  { value: "__ne", label: dunderOperatorLabel("ne") },
  ...DJANGO_LOOKUPS.map((lookup) => ({ value: `__${lookup}`, label: dunderOperatorLabel(lookup) })),
];
const AVAILABLE_OPERATOR_OPTIONS = [...OPERATOR_OPTIONS];

function normalizeValueItem(item) {
  if (item === undefined || item === null) {
    return "";
  }
  return String(item).trim();
}

function toValueList(rawValue, keepEmpty = false) {
  if (Array.isArray(rawValue)) {
    const normalized = rawValue.map((item) => normalizeValueItem(item));
    return keepEmpty ? normalized : normalized.filter((item) => item.length > 0);
  }

  if (rawValue === undefined || rawValue === null) {
    return [];
  }

  const text = String(rawValue);
  const splitValues = text.split(",").map((item) => item.trim());
  return keepEmpty ? splitValues : splitValues.filter((item) => item.length > 0);
}

function setConditionValueList(condition, values) {
  condition.value = values.map((value) => normalizeValueItem(value));
}

function getConditionScalarValue(condition) {
  if (Array.isArray(condition.value)) {
    return condition.value
      .map((item) => normalizeValueItem(item))
      .filter((item) => item.length > 0)
      .join(", ");
  }
  return normalizeValueItem(condition.value);
}

function getConditionRangeValues(condition) {
  const values = toValueList(condition.value, true);
  return [values[0] || "", values[1] || ""];
}

function resolveOperatorSpec(rawOperator) {
  const operatorValue = typeof rawOperator === "string" ? rawOperator.trim() : "";
  if (!operatorValue) {
    return { lookup: "exact", negated: false };
  }

  const withoutDunder = operatorValue.startsWith("__")
    ? operatorValue.slice(2)
    : operatorValue;

  if (withoutDunder.startsWith("not_")) {
    const lookup = withoutDunder.slice(4);
    const resolvedLookup = OPERATOR_ALIASES[lookup] || lookup;
    if (DJANGO_LOOKUP_SET.has(resolvedLookup)) {
      return { lookup: resolvedLookup, negated: true };
    }
  }

  if (Object.prototype.hasOwnProperty.call(OPERATOR_ALIASES, withoutDunder)) {
    return {
      lookup: OPERATOR_ALIASES[withoutDunder],
      negated: withoutDunder === "ne",
    };
  }

  if (Object.prototype.hasOwnProperty.call(FRONTEND_OPERATOR_LOOKUPS, withoutDunder)) {
    return {
      lookup: FRONTEND_OPERATOR_LOOKUPS[withoutDunder],
      negated: withoutDunder.startsWith("not_"),
    };
  }

  if (DJANGO_LOOKUP_SET.has(withoutDunder)) {
    return { lookup: withoutDunder, negated: false };
  }

  return { lookup: "exact", negated: false };
}

const TRANSFORM_DEFINITIONS = [
  { value: "count", label: "COUNT", djangoName: "Count" },
  { value: "sum", label: "SUM", djangoName: "Sum" },
  { value: "avg", label: "AVG", djangoName: "Avg" },
  { value: "min", label: "MIN", djangoName: "Min" },
  { value: "max", label: "MAX", djangoName: "Max" },
];

const TRANSFORM_MAP = TRANSFORM_DEFINITIONS.reduce((acc, definition) => {
  acc[definition.value] = definition;
  return acc;
}, {});

const TRANSFORM_OPTIONS = TRANSFORM_DEFINITIONS.map(({ value, label }) => ({
  value,
  label,
}));

function generateTransformId() {
  return `transform-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeConditionTransforms(condition) {
  if (!condition) return [];

  if (!Array.isArray(condition.transforms)) {
    const legacyValues = Array.isArray(condition.aggregates)
      ? condition.aggregates
      : condition.aggregate
      ? [condition.aggregate]
      : [];

    condition.transforms = legacyValues
      .map((value) => {
        const definition = TRANSFORM_MAP[value];
        if (!definition) return null;
        return {
          id: generateTransformId(),
          value: definition.value,
        };
      })
      .filter(Boolean);
  }

  const transforms = Array.isArray(condition.transforms) ? condition.transforms : [];
  const normalized = [];

  transforms.forEach((transform) => {
    const definition = TRANSFORM_MAP[transform.value];
    if (!definition) return;
    normalized.push({
      id: transform?.id || generateTransformId(),
      value: definition.value,
    });
  });

  condition.transforms = normalized;
  return normalized;
}

const queryState = createGroup();

const queryRoot = document.getElementById("query-root");
const readablePreview = document.getElementById("readable-preview");
const djangoPreview = document.getElementById("django-preview");
const previewWrapper = document.getElementById("preview-wrapper");
const previewToggleButton = document.getElementById("preview-toggle");
const PREVIEW_HIDDEN_CLASS = "is-hidden";

let latestDerivedTransformState = null;

function toDjangoPath(field) {
  return (field || "").replace(/\./g, "__");
}

function makeAlias(transformName, field) {
  const cleanField = (field || "value").replace(/[^a-zA-Z0-9]+/g, "_") || "value";
  return `${transformName}_${cleanField}`;
}

function rebuildDerivedTransformState() {
  latestDerivedTransformState = buildDerivedTransformState(queryState);
  return latestDerivedTransformState;
}

function getDerivedTransformState() {
  if (!latestDerivedTransformState) {
    latestDerivedTransformState = buildDerivedTransformState(queryState);
  }
  return latestDerivedTransformState;
}

function buildDerivedTransformState(rootGroup) {
  const transformsById = new Map();
  const aliasOptionsByGroupId = new Map();
  const aliasLookupByGroupId = new Map();
  const parentByGroupId = new Map();
  const childrenByGroupId = new Map();
  const transformsPerGroup = new Map();
  const allGroups = [];

  const visitGroup = (group, ancestors) => {
    allGroups.push(group);
    const currentTransforms = [];
    group.conditions.forEach((condition) => {
      normalizeConditionTransforms(condition);
      if (!condition.field) {
        condition.field = AVAILABLE_FIELDS[0] || "";
      }
      const transforms = Array.isArray(condition.transforms) ? condition.transforms : [];
      if (transforms.length === 0) {
        if (!condition.fieldRef && (!condition.field || !AVAILABLE_FIELDS.includes(condition.field))) {
          condition.field = AVAILABLE_FIELDS[0] || "";
        }
        return;
      }

      let sourceValue = condition.field || "";
      if (!sourceValue && AVAILABLE_FIELDS.length > 0) {
        sourceValue = AVAILABLE_FIELDS[0];
        condition.field = sourceValue;
      }
      const sourceKind = condition.fieldRef?.type === "alias" ? "alias" : "field";
      let previousAlias = "";

      transforms.forEach((transform, index) => {
        const definition = TRANSFORM_MAP[transform.value];
        if (!definition) return;
        const aliasSourceValue = index === 0 ? sourceValue : previousAlias || sourceValue;
        const aliasSourceKind = index === 0 ? sourceKind : "alias";
        const alias = makeAlias(transform.value, aliasSourceValue);
        const displaySource = aliasSourceValue || "*";

        const meta = {
          id: transform.id,
          alias,
          displayLabel: `${definition.label}(${displaySource})`,
          definition,
          behavior: "aggregation",
          conditionId: condition.id,
          groupId: group.id,
          ancestorGroupIds: [...ancestors],
          source: {
            kind: aliasSourceKind,
            value: aliasSourceValue || "",
          },
          transform,
        };

        transformsById.set(transform.id, meta);
        currentTransforms.push(meta);
        previousAlias = alias;
      });
    });

    group.groups.forEach((child) => {
      parentByGroupId.set(child.id, group.id);
      if (!childrenByGroupId.has(group.id)) {
        childrenByGroupId.set(group.id, []);
      }
      childrenByGroupId.get(group.id).push(child.id);
      visitGroup(child, [...ancestors, group.id]);
    });

    transformsPerGroup.set(group.id, currentTransforms);
  };

  visitGroup(rootGroup, []);

  const subtreeTransformsByGroupId = new Map();
  const collectSubtree = (groupId) => {
    const direct = transformsPerGroup.get(groupId) || [];
    const children = childrenByGroupId.get(groupId) || [];
    const collected = [...direct];
    children.forEach((childId) => {
      collected.push(...collectSubtree(childId));
    });
    subtreeTransformsByGroupId.set(groupId, collected);
    return collected;
  };

  collectSubtree(rootGroup.id);

  allGroups.forEach((group) => {
    const accessible = [];
    const subtreeTransforms = subtreeTransformsByGroupId.get(group.id) || [];
    accessible.push(...subtreeTransforms);

    let current = parentByGroupId.get(group.id);
    while (current) {
      const parentTransforms = transformsPerGroup.get(current) || [];
      accessible.push(...parentTransforms);
      current = parentByGroupId.get(current);
    }

    aliasOptionsByGroupId.set(group.id, accessible);
    const lookup = new Map();
    accessible.forEach((meta) => {
      lookup.set(meta.alias, meta);
    });
    aliasLookupByGroupId.set(group.id, lookup);
  });

  const referencedTransformIds = new Set();

  const ensureFieldValue = (condition) => {
    if (condition.fieldRef && condition.fieldRef.type === "alias") return;
    if (!condition.field || !AVAILABLE_FIELDS.includes(condition.field)) {
      condition.field = AVAILABLE_FIELDS[0] || "";
    }
  };

  const synchronizeGroup = (group) => {
    group.conditions.forEach((condition) => {
      let refMeta = null;
      if (condition.fieldRef?.type === "alias" && condition.fieldRef.transformId) {
        const candidate = transformsById.get(condition.fieldRef.transformId);
        if (candidate && (candidate.groupId === group.id || candidate.ancestorGroupIds.includes(group.id))) {
          refMeta = candidate;
        } else {
          delete condition.fieldRef;
        }
      }

      if (!refMeta) {
        const lookup = aliasLookupByGroupId.get(group.id);
        if (lookup && lookup.has(condition.field)) {
          refMeta = lookup.get(condition.field);
          condition.fieldRef = { type: "alias", transformId: refMeta.id };
        }
      }

      if (refMeta) {
        condition.field = refMeta.alias;
        referencedTransformIds.add(refMeta.id);
      } else {
        delete condition.fieldRef;
        ensureFieldValue(condition);
      }
    });

    group.groups.forEach((child) => synchronizeGroup(child));
  };

  synchronizeGroup(rootGroup);

  referencedTransformIds.forEach((transformId) => {
    const meta = transformsById.get(transformId);
    if (meta) {
      meta.behavior = "annotation";
    }
  });

  return {
    transformsById,
    aliasOptionsByGroupId,
    aliasLookupByGroupId,
    parentByGroupId,
    subtreeTransformsByGroupId,
    transformsPerGroup,
  };
}

function getFieldOptionsForGroup(groupId) {
  const options = AVAILABLE_FIELDS.map((field) => ({
    value: field,
    label: field,
    type: "field",
  }));

  const derived = getDerivedTransformState();
  const aliasOptions = derived.aliasOptionsByGroupId?.get(groupId) || [];
  aliasOptions.forEach((meta) => {
    options.push({
      value: meta.alias,
      label: `${meta.displayLabel} → ${meta.alias}`,
      type: "alias",
      transformId: meta.id,
    });
  });

  return options;
}

function getAliasMetaForCondition(condition) {
  if (!condition?.fieldRef || condition.fieldRef.type !== "alias") {
    return null;
  }
  const derived = getDerivedTransformState();
  return derived.transformsById.get(condition.fieldRef.transformId) || null;
}

function createGroup() {
  return {
    id: `group-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    logicalOperator: "AND",
    conditions: [],
    groups: [],
    negated: false,
  };
}

function createCondition() {
  return {
    id: `condition-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    field: AVAILABLE_FIELDS[0] || "",
    fieldRef: null,
    operator: AVAILABLE_OPERATOR_OPTIONS[0]?.value || "equals",
    value: "",
    negated: false,
    transforms: [],
  };
}

function renderApp() {
  if (!queryRoot) return;
  const derived = rebuildDerivedTransformState();
  queryRoot.innerHTML = "";
  queryRoot.appendChild(renderGroup(queryState, true));
  updatePreview(derived);
}

function renderGroup(group, isRoot = false, level = 0, onRemove) {
  const container = document.createElement("div");
  container.classList.add("group-container");
  if (isRoot) container.classList.add("root");
  if (group.negated) container.classList.add("negated");

  const header = document.createElement("div");
  header.className = "group-header";

  const meta = document.createElement("div");
  meta.className = "group-meta";

  const negationButton = document.createElement("button");
  negationButton.type = "button";
  negationButton.className = "btn btn-outline btn-sm";
  negationButton.textContent = group.negated ? "Remove NOT" : "Add NOT";
  if (group.negated) {
    negationButton.classList.add("btn-not-active");
  }
  negationButton.addEventListener("click", () => {
    group.negated = !group.negated;
    renderApp();
  });

  const badge = document.createElement("span");
  badge.className = "badge";
  const filterableConditionCount = group.conditions.filter((condition) => !condition.isVariableOnly).length;
  badge.textContent = `${filterableConditionCount + group.groups.length} rule(s)`;

  meta.appendChild(negationButton);
  meta.appendChild(badge);
  header.appendChild(meta);

  if (typeof onRemove === "function") {
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn btn-ghost btn-icon";
    removeButton.setAttribute("aria-label", "Remove group");
    removeButton.appendChild(createIcon("trash"));
    removeButton.addEventListener("click", () => {
      onRemove();
    });
    header.appendChild(removeButton);
  }

  container.appendChild(header);

  const variableOnlyConditions = group.conditions
    .map((condition, idx) => ({ condition, idx }))
    .filter(({ condition }) => condition.isVariableOnly);

  if (variableOnlyConditions.length > 0) {
    const variableEditor = document.createElement("div");
    variableEditor.className = "variable-editor";
    variableOnlyConditions.forEach(({ idx }) => {
      variableEditor.appendChild(renderVariableCondition(group, idx));
    });
    container.appendChild(variableEditor);
  }

  const itemsWrapper = document.createElement("div");
  itemsWrapper.className = "condition-and-groups";

  const allItems = [
    ...group.conditions
      .map((condition, index) => ({ type: "condition", condition, index }))
      .filter((item) => !item.condition.isVariableOnly),
    ...group.groups.map((childGroup, index) => ({ type: "group", group: childGroup, index })),
  ];

  allItems.forEach((item, idx) => {
    if (item.type === "condition") {
      itemsWrapper.appendChild(renderCondition(group, item.index));
    } else {
      itemsWrapper.appendChild(
        renderGroup(item.group, false, level + 1, () => {
          group.groups.splice(item.index, 1);
          renderApp();
        })
      );
    }

    if (idx < allItems.length - 1) {
      const operatorRow = document.createElement("div");
      operatorRow.className = "operator-row";

      const operatorButton = document.createElement("button");
      operatorButton.type = "button";
      operatorButton.className = "btn btn-outline btn-sm btn-operator";
      if (group.negated) {
        operatorButton.classList.add("negated");
      } else {
        operatorButton.classList.add(group.logicalOperator === "AND" ? "and" : "or");
      }
      operatorButton.textContent = group.logicalOperator;
      operatorButton.addEventListener("click", () => {
        group.logicalOperator = group.logicalOperator === "AND" ? "OR" : "AND";
        renderApp();
      });

      operatorRow.appendChild(operatorButton);
      itemsWrapper.appendChild(operatorRow);
    }
  });

  container.appendChild(itemsWrapper);

  const actions = document.createElement("div");
  actions.className = "group-actions";

  const addConditionButton = document.createElement("button");
  addConditionButton.type = "button";
  addConditionButton.className = "btn btn-outline btn-sm";
  addConditionButton.appendChild(createIcon("plus"));
  addConditionButton.appendChild(document.createTextNode("Add Condition"));
  addConditionButton.addEventListener("click", () => {
    group.conditions.push(createCondition());
    renderApp();
  });

  const addSubqueryButton = document.createElement("button");
  addSubqueryButton.type = "button";
  addSubqueryButton.className = "btn btn-outline btn-sm";
  addSubqueryButton.appendChild(createIcon("plus"));
  addSubqueryButton.appendChild(document.createTextNode("Add Subquery"));
  addSubqueryButton.addEventListener("click", () => {
    if (!TRANSFORM_OPTIONS.length) {
      window.alert("No subqueries are available.");
      return;
    }
    const newCondition = createCondition();
    newCondition.isVariableOnly = true;
    newCondition.__isPickingTransform = true;
    newCondition.__pendingTransform = {
      value: TRANSFORM_OPTIONS[0]?.value || "",
    };
    group.conditions.push(newCondition);
    renderApp();
  });

  const addGroupButton = document.createElement("button");
  addGroupButton.type = "button";
  addGroupButton.className = "btn btn-outline btn-sm";
  addGroupButton.appendChild(createIcon("plus"));
  addGroupButton.appendChild(document.createTextNode("Add Group"));
  addGroupButton.addEventListener("click", () => {
    group.groups.push(createGroup());
    renderApp();
  });

  actions.appendChild(addConditionButton);
  actions.appendChild(addSubqueryButton);
  actions.appendChild(addGroupButton);

  container.appendChild(actions);

  return container;
}

function renderCondition(parentGroup, index) {
  const condition = parentGroup.conditions[index];
  const row = document.createElement("div");
  row.className = "condition-row";

  const notButton = document.createElement("button");
  notButton.type = "button";
  notButton.className = "btn btn-outline btn-sm";
  notButton.textContent = "NOT";
  if (condition.negated) {
    notButton.classList.add("btn-not-active");
  }
  notButton.addEventListener("click", () => {
    condition.negated = !condition.negated;
    renderApp();
  });
  row.appendChild(notButton);

  const transforms = normalizeConditionTransforms(condition);
  const derived = getDerivedTransformState();

  const transformList = document.createElement("div");
  transformList.className = "transform-list";

  transforms.forEach((transform, transformIndex) => {
    const definition = TRANSFORM_MAP[transform.value];
    if (!definition) return;

    const transformItem = document.createElement("div");
    transformItem.className = "transform-item";

    const meta = derived.transformsById?.get(transform.id);
    const behavior = meta?.behavior === "annotation" ? "annotation" : "aggregation";
    const aliasName = meta?.alias || makeAlias(transform.value, meta?.source?.value || condition.field || "value");
    const displaySource = meta?.displayLabel || `${definition.label}(${meta?.source?.value || condition.field || "*"})`;
    const variableWrapper = document.createElement("div");
    variableWrapper.className = "transform-variable";
    const variableHeader = document.createElement("div");
    variableHeader.className = "transform-variable-header";
    const typeBadge = document.createElement("span");
    typeBadge.className = `transform-badge transform-badge-${behavior}`;
    typeBadge.textContent = behavior === "annotation" ? "Annotation" : "Aggregation";
    variableHeader.appendChild(typeBadge);
    const aliasPill = document.createElement("span");
    aliasPill.className = "transform-alias";
    aliasPill.textContent = aliasName;
    variableHeader.appendChild(aliasPill);
    const variableHint = document.createElement("div");
    variableHint.className = "transform-variable-hint";
    variableHint.textContent = displaySource;
    variableWrapper.appendChild(variableHeader);
    variableWrapper.appendChild(variableHint);
    transformItem.appendChild(variableWrapper);

    const functionSelect = document.createElement("select");
    TRANSFORM_OPTIONS.forEach((option) => {
      const opt = document.createElement("option");
      opt.value = option.value;
      opt.textContent = option.label;
      functionSelect.appendChild(opt);
    });
    functionSelect.value = transform.value;
    functionSelect.addEventListener("change", (event) => {
      const newValue = event.target.value;
      if (!TRANSFORM_MAP[newValue]) return;
      condition.transforms[transformIndex].value = newValue;
      renderApp();
    });
    transformItem.appendChild(functionSelect);

    transformList.appendChild(transformItem);
  });

  if (transforms.length > 0) {
    row.appendChild(transformList);
  }

  const shouldRenderTransformControl = condition.isVariableOnly || transforms.length > 0 || condition.__isPickingTransform;
  if (shouldRenderTransformControl) {
    const transformControl = document.createElement("div");
    transformControl.className = "transform-control";

    const resetTransformPicker = () => {
      delete condition.__pendingTransform;
      delete condition.__isPickingTransform;
    };

    if (condition.__isPickingTransform) {
      const functionSelect = document.createElement("select");
      TRANSFORM_OPTIONS.forEach((option) => {
        const opt = document.createElement("option");
        opt.value = option.value;
        opt.textContent = option.label;
        functionSelect.appendChild(opt);
      });
      functionSelect.value = condition.__pendingTransform?.value || TRANSFORM_OPTIONS[0]?.value || "";
      functionSelect.addEventListener("change", (event) => {
        condition.__pendingTransform.value = event.target.value;
      });
      transformControl.appendChild(functionSelect);

      const applyButton = document.createElement("button");
      applyButton.type = "button";
      applyButton.className = "btn btn-outline btn-sm transform-confirm-button";
      applyButton.textContent = "Save";
      applyButton.addEventListener("click", () => {
        const pendingValue = condition.__pendingTransform?.value || TRANSFORM_OPTIONS[0]?.value || "";
        if (!pendingValue) {
          window.alert("Select a subquery before applying.");
          return;
        }
        if (!Array.isArray(condition.transforms)) {
          condition.transforms = [];
        }
        if (condition.transforms.length === 0) {
          condition.transforms.push({
            id: generateTransformId(),
            value: pendingValue,
          });
        } else {
          condition.transforms[0].value = pendingValue;
        }
        resetTransformPicker();
        renderApp();
      });
      transformControl.appendChild(applyButton);

      const cancelButton = document.createElement("button");
      cancelButton.type = "button";
      cancelButton.className = "btn btn-ghost btn-sm transform-cancel-button";
      cancelButton.textContent = "Cancel";
      cancelButton.addEventListener("click", () => {
        resetTransformPicker();
        renderApp();
      });
      transformControl.appendChild(cancelButton);
    } else {
      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "btn btn-outline btn-sm btn-icon-only transform-edit-button";
      editButton.setAttribute("title", transforms.length > 0 ? "Edit subquery" : "Add subquery");
      editButton.setAttribute("aria-label", transforms.length > 0 ? "Edit subquery" : "Add subquery");
      editButton.appendChild(createIcon("pen"));
      editButton.addEventListener("click", () => {
        if (!TRANSFORM_OPTIONS.length) {
          window.alert("No subqueries are available.");
          return;
        }
        const initialValue = transforms[0]?.value || TRANSFORM_OPTIONS[0]?.value || "";
        condition.__pendingTransform = {
          value: initialValue,
        };
        condition.__isPickingTransform = true;
        renderApp();
      });
      editButton.disabled = TRANSFORM_OPTIONS.length === 0;
      transformControl.appendChild(editButton);
    }

    row.appendChild(transformControl);
  }

  const fieldSelect = document.createElement("select");
  const fieldOptions = getFieldOptionsForGroup(parentGroup.id);
  if (fieldOptions.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No fields available";
    fieldSelect.appendChild(option);
    fieldSelect.disabled = true;
  } else {
    fieldOptions.forEach((optionDef) => {
      const option = document.createElement("option");
      option.value = optionDef.value;
      option.textContent = optionDef.label;
      if (optionDef.type === "alias" && optionDef.transformId) {
        option.dataset.transformId = optionDef.transformId;
      }
      fieldSelect.appendChild(option);
    });
    if (!fieldOptions.some((option) => option.value === condition.field)) {
      condition.field = fieldOptions[0].value;
    }
  }
  fieldSelect.value = condition.field;
  fieldSelect.addEventListener("change", (event) => {
    const selectElement = event.target;
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    const transformId = selectedOption?.dataset?.transformId;
    condition.field = selectElement.value;
    if (transformId) {
      condition.fieldRef = { type: "alias", transformId };
    } else {
      delete condition.fieldRef;
    }
    renderApp();
  });
  row.appendChild(fieldSelect);

  const operatorSelect = document.createElement("select");
  AVAILABLE_OPERATOR_OPTIONS.forEach((operator) => {
    const option = document.createElement("option");
    option.value = operator.value;
    option.textContent = operator.label;
    operatorSelect.appendChild(option);
  });
  if (!AVAILABLE_OPERATOR_OPTIONS.some((option) => option.value === condition.operator)) {
    condition.operator = AVAILABLE_OPERATOR_OPTIONS[0]?.value || "equals";
  }
  operatorSelect.value = condition.operator;
  operatorSelect.addEventListener("change", (event) => {
    condition.operator = event.target.value;
    renderApp();
  });
  row.appendChild(operatorSelect);

  const conditionRemoveButton = document.createElement("button");
  conditionRemoveButton.type = "button";
  conditionRemoveButton.className = "btn btn-ghost btn-icon";
  conditionRemoveButton.setAttribute("aria-label", "Remove condition");
  conditionRemoveButton.appendChild(createIcon("trash"));
  conditionRemoveButton.addEventListener("click", () => {
    parentGroup.conditions.splice(index, 1);
    renderApp();
  });
  let isConditionRemoveInline = false;

  const operatorSpec = resolveOperatorSpec(condition.operator);
  if (operatorSpec.lookup === "range") {
    const values = getConditionRangeValues(condition);
    const valueGroup = document.createElement("div");
    valueGroup.className = "condition-value-group";

    const startInput = document.createElement("input");
    startInput.type = "text";
    startInput.placeholder = "From";
    startInput.value = values[0];

    const endInput = document.createElement("input");
    endInput.type = "text";
    endInput.placeholder = "To";
    endInput.value = values[1];

    const syncRangeValues = () => {
      setConditionValueList(condition, [startInput.value, endInput.value]);
      updatePreview();
    };

    startInput.addEventListener("input", syncRangeValues);
    endInput.addEventListener("input", syncRangeValues);
    valueGroup.appendChild(startInput);
    valueGroup.appendChild(endInput);
    row.appendChild(valueGroup);
  } else if (operatorSpec.lookup === "in") {
    const valueGroup = document.createElement("div");
    valueGroup.className = "condition-value-group condition-value-group-list";

    const valueList = document.createElement("div");
    valueList.className = "condition-value-list";
    const values = toValueList(condition.value);
    setConditionValueList(condition, values);
    if (values.length === 0) {
      const empty = document.createElement("span");
      empty.className = "condition-value-empty";
      empty.textContent = "No values yet";
      valueList.appendChild(empty);
    } else {
      values.forEach((value, valueIndex) => {
        const item = document.createElement("span");
        item.className = "condition-value-item";

        const label = document.createElement("span");
        label.className = "condition-value-chip";
        label.textContent = value;
        item.appendChild(label);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "btn btn-ghost btn-sm condition-value-remove";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () => {
          const nextValues = toValueList(condition.value);
          nextValues.splice(valueIndex, 1);
          setConditionValueList(condition, nextValues);
          renderApp();
        });
        item.appendChild(removeButton);
        valueList.appendChild(item);
      });
    }
    valueGroup.appendChild(valueList);

    const valueControls = document.createElement("div");
    valueControls.className = "condition-value-controls";
    const addInput = document.createElement("input");
    addInput.type = "text";
    addInput.placeholder = "Add value";
    const addButton = document.createElement("button");
    addButton.type = "button";
    addButton.className = "btn btn-outline btn-sm";
    addButton.textContent = "Add";

    const addValue = () => {
      const nextValue = normalizeValueItem(addInput.value);
      if (!nextValue) return;
      const nextValues = toValueList(condition.value);
      nextValues.push(nextValue);
      setConditionValueList(condition, nextValues);
      renderApp();
    };

    addInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      addValue();
    });
    addButton.addEventListener("click", addValue);

    valueControls.appendChild(addInput);
    valueControls.appendChild(addButton);
    valueControls.appendChild(conditionRemoveButton);
    isConditionRemoveInline = true;
    valueGroup.appendChild(valueControls);
    row.appendChild(valueGroup);
  } else {
    const valueInput = document.createElement("input");
    valueInput.type = "text";
    valueInput.placeholder = "Value";
    valueInput.value = getConditionScalarValue(condition);
    valueInput.addEventListener("input", (event) => {
      condition.value = event.target.value;
      updatePreview();
    });
    row.appendChild(valueInput);
  }
  if (!isConditionRemoveInline) {
    row.appendChild(conditionRemoveButton);
  }

  return row;
}

function renderVariableCondition(parentGroup, index) {
  const condition = parentGroup.conditions[index];
  const row = document.createElement("div");
  row.className = "variable-row";

  const transforms = normalizeConditionTransforms(condition);
  const derived = getDerivedTransformState();

  const transformList = document.createElement("div");
  transformList.className = "transform-list";

  transforms.forEach((transform, transformIndex) => {
    const definition = TRANSFORM_MAP[transform.value];
    if (!definition) return;

    const transformItem = document.createElement("div");
    transformItem.className = "transform-item";

    const meta = derived.transformsById?.get(transform.id);
    const behavior = meta?.behavior === "annotation" ? "annotation" : "aggregation";
    const aliasName = meta?.alias || makeAlias(transform.value, meta?.source?.value || condition.field || "value");
    const displaySource = meta?.displayLabel || `${definition.label}(${meta?.source?.value || condition.field || "*"})`;
    const variableWrapper = document.createElement("div");
    variableWrapper.className = "transform-variable";
    const variableHeader = document.createElement("div");
    variableHeader.className = "transform-variable-header";
    const typeBadge = document.createElement("span");
    typeBadge.className = `transform-badge transform-badge-${behavior}`;
    typeBadge.textContent = behavior === "annotation" ? "Annotation" : "Aggregation";
    variableHeader.appendChild(typeBadge);
    const aliasPill = document.createElement("span");
    aliasPill.className = "transform-alias";
    aliasPill.textContent = aliasName;
    variableHeader.appendChild(aliasPill);
    const variableHint = document.createElement("div");
    variableHint.className = "transform-variable-hint";
    variableHint.textContent = displaySource;
    variableWrapper.appendChild(variableHeader);
    variableWrapper.appendChild(variableHint);
    transformItem.appendChild(variableWrapper);

    const functionSelect = document.createElement("select");
    TRANSFORM_OPTIONS.forEach((option) => {
      const opt = document.createElement("option");
      opt.value = option.value;
      opt.textContent = option.label;
      functionSelect.appendChild(opt);
    });
    functionSelect.value = transform.value;
    functionSelect.addEventListener("change", (event) => {
      const newValue = event.target.value;
      if (!TRANSFORM_MAP[newValue]) return;
      condition.transforms[transformIndex].value = newValue;
      renderApp();
    });
    transformItem.appendChild(functionSelect);

    transformList.appendChild(transformItem);
  });

  if (transforms.length > 0) {
    row.appendChild(transformList);
  }

  const transformControl = document.createElement("div");
  transformControl.className = "transform-control";

  const resetTransformPicker = () => {
    delete condition.__pendingTransform;
    delete condition.__isPickingTransform;
  };

  if (condition.__isPickingTransform) {
    const functionSelect = document.createElement("select");
    TRANSFORM_OPTIONS.forEach((option) => {
      const opt = document.createElement("option");
      opt.value = option.value;
      opt.textContent = option.label;
      functionSelect.appendChild(opt);
    });
    functionSelect.value = condition.__pendingTransform?.value || TRANSFORM_OPTIONS[0]?.value || "";
    functionSelect.addEventListener("change", (event) => {
      condition.__pendingTransform.value = event.target.value;
    });
    transformControl.appendChild(functionSelect);

    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "btn btn-outline btn-sm transform-confirm-button";
    applyButton.textContent = "Save";
    applyButton.addEventListener("click", () => {
      const pendingValue = condition.__pendingTransform?.value || TRANSFORM_OPTIONS[0]?.value || "";
      if (!pendingValue) {
        window.alert("Select a subquery before applying.");
        return;
      }
      if (!Array.isArray(condition.transforms)) {
        condition.transforms = [];
      }
      if (condition.transforms.length === 0) {
        condition.transforms.push({
          id: generateTransformId(),
          value: pendingValue,
        });
      } else {
        condition.transforms[0].value = pendingValue;
      }
      resetTransformPicker();
      renderApp();
    });
    transformControl.appendChild(applyButton);

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "btn btn-ghost btn-sm transform-cancel-button";
    cancelButton.textContent = "Cancel";
    cancelButton.addEventListener("click", () => {
      resetTransformPicker();
      renderApp();
    });
    transformControl.appendChild(cancelButton);
  } else {
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "btn btn-outline btn-sm btn-icon-only transform-edit-button";
    editButton.setAttribute("title", transforms.length > 0 ? "Edit subquery" : "Add subquery");
    editButton.setAttribute("aria-label", transforms.length > 0 ? "Edit subquery" : "Add subquery");
    editButton.appendChild(createIcon("pen"));
    editButton.addEventListener("click", () => {
      if (!TRANSFORM_OPTIONS.length) {
        window.alert("No subqueries are available.");
        return;
      }
      const initialValue = transforms[0]?.value || TRANSFORM_OPTIONS[0]?.value || "";
      condition.__pendingTransform = {
        value: initialValue,
      };
      condition.__isPickingTransform = true;
      renderApp();
    });
    editButton.disabled = TRANSFORM_OPTIONS.length === 0;
    transformControl.appendChild(editButton);
  }

  row.appendChild(transformControl);

  const fieldSelect = document.createElement("select");
  const fieldOptions = getFieldOptionsForGroup(parentGroup.id);
  if (fieldOptions.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No fields available";
    fieldSelect.appendChild(option);
    fieldSelect.disabled = true;
  } else {
    fieldOptions.forEach((optionDef) => {
      const option = document.createElement("option");
      option.value = optionDef.value;
      option.textContent = optionDef.label;
      if (optionDef.type === "alias" && optionDef.transformId) {
        option.dataset.transformId = optionDef.transformId;
      }
      fieldSelect.appendChild(option);
    });
    if (!fieldOptions.some((option) => option.value === condition.field)) {
      condition.field = fieldOptions[0].value;
    }
  }
  fieldSelect.value = condition.field;
  fieldSelect.addEventListener("change", (event) => {
    const selectElement = event.target;
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    const transformId = selectedOption?.dataset?.transformId;
    condition.field = selectElement.value;
    if (transformId) {
      condition.fieldRef = { type: "alias", transformId };
    } else {
      delete condition.fieldRef;
    }
    renderApp();
  });
  row.appendChild(fieldSelect);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "btn btn-ghost btn-icon";
  removeButton.setAttribute("aria-label", "Remove variable");
  removeButton.appendChild(createIcon("trash"));
  removeButton.addEventListener("click", () => {
    parentGroup.conditions.splice(index, 1);
    renderApp();
  });
  row.appendChild(removeButton);

  return row;
}

function initializePreviewToggle() {
  if (!previewWrapper || !previewToggleButton) return;

  const setState = (isHidden) => {
    previewWrapper.setAttribute("aria-hidden", String(isHidden));
    previewToggleButton.setAttribute("aria-expanded", String(!isHidden));
    previewToggleButton.textContent = isHidden ? "Show Preview" : "Hide Preview";
  };

  setState(previewWrapper.classList.contains(PREVIEW_HIDDEN_CLASS));

  previewToggleButton.addEventListener("click", () => {
    const isHidden = previewWrapper.classList.toggle(PREVIEW_HIDDEN_CLASS);
    setState(isHidden);
  });
}

function createIcon(name) {
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");

  if (name === "plus") {
    const path1 = document.createElementNS(svgNS, "path");
    path1.setAttribute("d", "M12 5v14");
    path1.setAttribute("stroke-linecap", "round");
    path1.setAttribute("stroke-linejoin", "round");

    const path2 = document.createElementNS(svgNS, "path");
    path2.setAttribute("d", "M5 12h14");
    path2.setAttribute("stroke-linecap", "round");
    path2.setAttribute("stroke-linejoin", "round");

    svg.appendChild(path1);
    svg.appendChild(path2);
  }

  if (name === "pen") {
    const path1 = document.createElementNS(svgNS, "path");
    path1.setAttribute("d", "M16.862 4.487a2 2 0 0 1 2.65 2.65l-9.19 9.19a2 2 0 0 1-.879.506l-3.004.834.834-3.004a2 2 0 0 1 .506-.879l9.19-9.19Z");
    path1.setAttribute("stroke-linejoin", "round");
    const path2 = document.createElementNS(svgNS, "path");
    path2.setAttribute("d", "M15 5.5 18.5 9");
    path2.setAttribute("stroke-linecap", "round");

    svg.appendChild(path1);
    svg.appendChild(path2);
  }

  if (name === "trash") {
    const path1 = document.createElementNS(svgNS, "path");
    path1.setAttribute("d", "M3 6h18");
    path1.setAttribute("stroke-linecap", "round");

    const path2 = document.createElementNS(svgNS, "path");
    path2.setAttribute("d", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2");
    path2.setAttribute("stroke-linecap", "round");

    const path3 = document.createElementNS(svgNS, "path");
    path3.setAttribute("d", "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6");
    path3.setAttribute("stroke-linecap", "round");
    path3.setAttribute("stroke-linejoin", "round");

    const path4 = document.createElementNS(svgNS, "path");
    path4.setAttribute("d", "M10 11v6");
    path4.setAttribute("stroke-linecap", "round");

    const path5 = document.createElementNS(svgNS, "path");
    path5.setAttribute("d", "M14 11v6");
    path5.setAttribute("stroke-linecap", "round");

    svg.appendChild(path1);
    svg.appendChild(path2);
    svg.appendChild(path3);
    svg.appendChild(path4);
    svg.appendChild(path5);
  }

  return svg;
}

function updatePreview(existingDerivedState) {
  if (!readablePreview || !djangoPreview) return;

  if (existingDerivedState) {
    latestDerivedTransformState = existingDerivedState;
  } else {
    rebuildDerivedTransformState();
  }

  const readable = generateQueryString(queryState, 0, true);
  if (readable.trim().length === 0) {
    readablePreview.textContent = "No conditions defined";
  } else {
    readablePreview.textContent = readable;
  }

  djangoPreview.textContent = generateDjangoORM(queryState);
}

function generateQueryString(group, indent = 0, isRoot = false) {
  const indentation = "  ".repeat(indent);
  let result = "";
  const derived = getDerivedTransformState();

  if (!isRoot) {
    if (group.negated) {
      result += `${indentation}NOT (\n`;
    } else {
      result += `${indentation}(\n`;
    }
  } else if (group.negated) {
    result += `${indentation}NOT (\n`;
  }

  const items = [];

  group.conditions.forEach((condition) => {
    if (condition.isVariableOnly) {
      return;
    }
    const operatorSpec = resolveOperatorSpec(condition.operator);
    const operatorLabel =
      AVAILABLE_OPERATOR_OPTIONS.find((option) => option.value === condition.operator)?.label ||
      OPERATOR_OPTIONS.find((option) => option.value === condition.operator)?.label ||
      condition.operator;
    const transforms = normalizeConditionTransforms(condition);
    const transformMetas = transforms
      .map((transform) => derived.transformsById.get(transform.id))
      .filter(Boolean);
    const lastTransformMeta = transformMetas[transformMetas.length - 1];
    const isAggregationOnly = transformMetas.length > 0 && (!lastTransformMeta || lastTransformMeta.behavior !== "annotation");
    const aliasMeta = getAliasMetaForCondition(condition);
    const baseField = aliasMeta ? aliasMeta.displayLabel || aliasMeta.alias : condition.field || "*";
    const fieldLabel =
      transforms.length > 0
        ? transforms.reduce((acc, transform) => {
            const definition = TRANSFORM_MAP[transform.value];
            return definition ? `${definition.label}(${acc})` : acc;
          }, baseField)
        : baseField;

    if (isAggregationOnly) {
      const aggregationDescription =
        transformMetas.length > 0
          ? transformMetas.map((meta) => meta?.displayLabel || "").filter(Boolean).join(" → ")
          : fieldLabel;
      const aggregationLine = `${"  ".repeat(indent + 1)}Aggregation: ${aggregationDescription || fieldLabel}`;
      items.push(aggregationLine);
      return;
    }

    const valueLabel =
      operatorSpec.lookup === "in" || operatorSpec.lookup === "range"
        ? `[${toValueList(condition.value).join(", ")}]`
        : `"${getConditionScalarValue(condition)}"`;
    const prefix = condition.negated ? "NOT " : "";
    const line = `${"  ".repeat(indent + 1)}${prefix}${fieldLabel} ${operatorLabel} ${valueLabel}`;
    items.push(line);
  });

  group.groups.forEach((nestedGroup) => {
    items.push(generateQueryString(nestedGroup, indent + 1, false));
  });

  if (items.length > 0) {
    result += items.join(`\n${"  ".repeat(indent + 1)}${group.logicalOperator}\n`);
  }

  if (!isRoot || group.negated) {
    result += `\n${indentation})`;
  }

  return result;
}

function generateDjangoORM(group) {
  const annotations = new Map();
  const aggregations = new Map();
  const imports = new Set();
  const derived = getDerivedTransformState();

  const escapeValue = (value) => value.replace(/\\/g, "\\\\").replace(/'/g, "\\'");

  const formatBoolean = (value) => (value.toLowerCase() === "true" ? "True" : "False");

  const formatScalarValue = (raw) => {
    const trimmed = normalizeValueItem(raw);
    if (trimmed.length === 0) {
      return "''";
    }
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
      return trimmed;
    }
    if (/^(true|false)$/i.test(trimmed)) {
      return formatBoolean(trimmed);
    }
    if (/^(none|null)$/i.test(trimmed)) {
      return "None";
    }
    return `'${escapeValue(trimmed)}'`;
  };

  const formatListValue = (raw) => {
    const parts = toValueList(raw).map((item) => formatScalarValue(item));

    return `[${parts.join(", ")}]`;
  };

  const formatValue = (value, lookup) => {
    if (lookup === "in" || lookup === "range") {
      return formatListValue(value);
    }
    return formatScalarValue(value);
  };

  const registerTransformMeta = (meta) => {
    if (!meta || !meta.definition) return;
    const sourceValue =
      meta.source.kind === "alias" ? meta.source.value : toDjangoPath(meta.source.value || "pk");
    const expression = `${meta.definition.djangoName}('${sourceValue}')`;
    imports.add(meta.definition.djangoName);
    if (meta.behavior === "annotation") {
      if (!annotations.has(meta.alias)) {
        annotations.set(meta.alias, expression);
      }
    } else if (!aggregations.has(meta.alias)) {
      aggregations.set(meta.alias, expression);
    }
  };

  const buildQ = (g, isRoot = true) => {
    const parts = [];

    g.conditions.forEach((condition) => {
      const operatorSpec = resolveOperatorSpec(condition.operator);
      const suffix = operatorSpec.lookup === "exact" ? "" : `__${operatorSpec.lookup}`;
      let isNegated = condition.negated || operatorSpec.negated;

      const transforms = normalizeConditionTransforms(condition);
      const transformMetas = transforms
        .map((transform) => derived.transformsById.get(transform.id))
        .filter(Boolean);
      transformMetas.forEach(registerTransformMeta);
      if (condition.isVariableOnly) {
        return;
      }
      const lastMeta = transformMetas[transformMetas.length - 1];
      const isFilterable = transformMetas.length === 0 || (lastMeta && lastMeta.behavior === "annotation");
      if (!isFilterable && transformMetas.length > 0) {
        return;
      }

      const aliasMeta = getAliasMetaForCondition(condition);
      let targetPath = "";
      if (transformMetas.length > 0 && lastMeta) {
        targetPath = lastMeta.alias;
      } else if (aliasMeta) {
        targetPath = aliasMeta.alias;
      } else {
        targetPath = toDjangoPath(condition.field);
      }
      if (!targetPath) {
        targetPath = "pk";
      }

      const valueExpression = formatValue(condition.value, operatorSpec.lookup);

      const qObject = `Q(${targetPath}${suffix}=${valueExpression})`;
      const expression = isNegated ? `~(${qObject})` : qObject;
      parts.push(expression);
    });

    g.groups.forEach((child) => {
      const childExpression = buildQ(child, false);
      if (childExpression) {
        parts.push(childExpression);
      }
    });

    if (parts.length === 0) {
      return isRoot ? "Q()" : "";
    }

    const joiner = g.logicalOperator === "AND" ? " & " : " | ";
    const combined = parts.join(joiner);

    if (g.negated) {
      const wrapped = parts.length === 1 ? combined : `(${combined})`;
      return `~(${wrapped})`;
    }

    if (!isRoot && parts.length > 1) {
      return `(${combined})`;
    }

    return parts.length === 1 ? parts[0] : combined;
  };

  const expression = buildQ(group, true);

  const annotationEntries = Array.from(annotations.entries());
  const aggregationEntries = Array.from(aggregations.entries());

  let filterExpression = expression;
  let filterLine = "";
  let requiresQ = false;

  if (!filterExpression || filterExpression === "Q()") {
    filterLine = "";
  } else {
    const isSimple =
      !filterExpression.includes("&") &&
      !filterExpression.includes("|") &&
      !filterExpression.startsWith("~");

    if (isSimple && filterExpression.startsWith("Q(") && filterExpression.endsWith(")")) {
      filterExpression = filterExpression.slice(2, -1);
    }

    if (
      filterExpression.includes("Q(") ||
      filterExpression.includes("~(") ||
      filterExpression.includes("&") ||
      filterExpression.includes("|")
    ) {
      requiresQ = true;
    }

    filterLine = `    .filter(${filterExpression})`;
  }

  if (requiresQ) {
    imports.add("Q");
  }

  const importList = Array.from(imports).sort((a, b) => {
    if (a === "Q") return -1;
    if (b === "Q") return 1;
    return a.localeCompare(b);
  });

  let result = "";
  if (importList.length > 0) {
    result = `from django.db.models import ${importList.join(", ")}`;
  }

  const chainLines = ["    queryset"];

  if (annotationEntries.length === 1) {
    const [alias, fn] = annotationEntries[0];
    chainLines.push(`    .annotate(${alias}=${fn})`);
  } else if (annotationEntries.length > 1) {
    chainLines.push("    .annotate(");
    annotationEntries.forEach(([alias, fn], index) => {
      const suffix = index === annotationEntries.length - 1 ? "" : ",";
      chainLines.push(`        ${alias}=${fn}${suffix}`);
    });
    chainLines.push("    )");
  }

  if (filterLine) {
    chainLines.push(filterLine);
  }

  let querysetBlock = "";
  if (chainLines.length === 1) {
    querysetBlock = "queryset = queryset";
  } else {
    querysetBlock = `queryset = (\n${chainLines.join("\n")}\n)`;
  }

  const aggregateLines = [];
  if (aggregationEntries.length === 1) {
    const [alias, fn] = aggregationEntries[0];
    aggregateLines.push(`result = queryset.aggregate(${alias}=${fn})`);
  } else if (aggregationEntries.length > 1) {
    aggregateLines.push("result = queryset.aggregate(");
    aggregationEntries.forEach(([alias, fn], index) => {
      const suffix = index === aggregationEntries.length - 1 ? "" : ",";
      aggregateLines.push(`    ${alias}=${fn}${suffix}`);
    });
    aggregateLines.push(")");
  }

  result = result ? `${result}\n\n${querysetBlock}` : querysetBlock;
  if (aggregateLines.length > 0) {
    const aggregateBlock = aggregateLines.join("\n");
    result = result ? `${result}\n\n${aggregateBlock}` : aggregateBlock;
  }

  return result;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    AVAILABLE_FIELDS,
    OPERATOR_OPTIONS,
    AVAILABLE_OPERATOR_OPTIONS,
    TRANSFORM_DEFINITIONS,
    TRANSFORM_MAP,
    TRANSFORM_OPTIONS,
    createGroup,
    createCondition,
    normalizeConditionTransforms,
    generateQueryString,
    generateDjangoORM,
    buildDerivedTransformState,
    rebuildDerivedTransformState,
    getDerivedTransformState,
    getFieldOptionsForGroup,
    renderApp,
    queryState,
    makeAlias,
    toDjangoPath,
  };
}

initializePreviewToggle();
renderApp();
