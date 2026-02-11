const DEFAULT_AVAILABLE_FIELDS = [];

function getBuilderConfig() {
  const jsonNode = document.getElementById("advanced-query-builder-config");
  if (jsonNode?.textContent) {
    try {
      return JSON.parse(jsonNode.textContent);
    } catch (error) {
      console.warn("Failed to parse advanced query builder config.", error);
    }
  }

  if (typeof window !== "undefined" && window.ADVANCED_QUERY_BUILDER_CONFIG) {
    return window.ADVANCED_QUERY_BUILDER_CONFIG;
  }

  return {};
}

const BUILDER_CONFIG = getBuilderConfig();
const ENABLE_TRANSFORMS = BUILDER_CONFIG?.enableTransforms !== false;

function resolveAvailableFields(config) {
  const configured = config?.availableFields;
  if (!Array.isArray(configured)) {
    return [...DEFAULT_AVAILABLE_FIELDS];
  }

  const cleaned = configured
    .filter((field) => typeof field === "string")
    .map((field) => field.trim())
    .filter((field) => field.length > 0);

  if (cleaned.length === 0) {
    return [...DEFAULT_AVAILABLE_FIELDS];
  }

  return Array.from(new Set(cleaned));
}

const AVAILABLE_FIELDS = resolveAvailableFields(BUILDER_CONFIG);
const ADVANCED_QUERY_PARAM = typeof BUILDER_CONFIG?.queryParam === "string" && BUILDER_CONFIG.queryParam.trim()
  ? BUILDER_CONFIG.queryParam.trim()
  : "advanced_query";
const INITIAL_QUERY_PAYLOAD = typeof BUILDER_CONFIG?.initialQuery === "string"
  ? BUILDER_CONFIG.initialQuery
  : "";

const OPERATOR_OPTIONS = [
  { value: "equals", label: "Equals" },
  { value: "not_equals", label: "Not Equals" },
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Not Contains" },
  { value: "greater_than", label: "Greater Than" },
  { value: "less_than", label: "Less Than" },
  { value: "in", label: "In" },
  { value: "not_in", label: "Not In" },
];

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

const TRANSFORM_OPTIONS = ENABLE_TRANSFORMS
  ? TRANSFORM_DEFINITIONS.map(({ value, label }) => ({
      value,
      label,
    }))
  : [];

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
const applyQueryButton = document.getElementById("advanced-query-apply");
const clearQueryButton = document.getElementById("advanced-query-clear");
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

function getRenderableItems(group) {
  return [
    ...group.conditions
      .map((condition, index) => ({ type: "condition", condition, index }))
      .filter((item) => !item.condition.isVariableOnly),
    ...group.groups.map((childGroup, index) => ({ type: "group", group: childGroup, index })),
  ];
}

function ensureGroupOperators(group) {
  const items = getRenderableItems(group);
  const expectedLength = Math.max(items.length - 1, 0);
  const fallback = group.logicalOperator === "OR" ? "OR" : "AND";

  if (!Array.isArray(group.operators)) {
    group.operators = [];
  }

  const sanitized = group.operators
    .map((value) => (value === "OR" ? "OR" : value === "AND" ? "AND" : fallback))
    .slice(0, expectedLength);

  while (sanitized.length < expectedLength) {
    sanitized.push(fallback);
  }

  group.operators = sanitized;
  return sanitized;
}

function getGroupOperatorAt(group, index) {
  const operators = ensureGroupOperators(group);
  if (index < 0 || index >= operators.length) {
    return "AND";
  }
  return operators[index];
}

function setGroupOperatorAt(group, index, operator) {
  const operators = ensureGroupOperators(group);
  if (index < 0 || index >= operators.length) {
    return;
  }
  operators[index] = operator === "OR" ? "OR" : "AND";
  group.operators = operators;
}

function generateGroupId() {
  return `group-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function generateConditionId() {
  return `condition-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createGroup() {
  return {
    id: generateGroupId(),
    logicalOperator: "AND",
    operators: [],
    conditions: [],
    groups: [],
    negated: false,
  };
}

function createCondition() {
  return {
    id: generateConditionId(),
    field: AVAILABLE_FIELDS[0] || "",
    fieldRef: null,
    operator: "equals",
    value: "",
    negated: false,
    transforms: [],
  };
}

function hydrateCondition(condition) {
  const normalized = createCondition();
  if (!condition || typeof condition !== "object") {
    return normalized;
  }

  if (typeof condition.id === "string" && condition.id.trim()) {
    normalized.id = condition.id;
  }
  if (typeof condition.field === "string") {
    normalized.field = condition.field;
  }
  if (typeof condition.operator === "string") {
    normalized.operator = condition.operator;
  }
  if (Array.isArray(condition.value)) {
    normalized.value = condition.value.join(", ");
  } else if (condition.value !== undefined && condition.value !== null) {
    normalized.value = String(condition.value);
  } else {
    normalized.value = "";
  }
  normalized.negated = Boolean(condition.negated);
  normalized.isVariableOnly = Boolean(condition.isVariableOnly);

  if (Array.isArray(condition.transforms)) {
    normalized.transforms = condition.transforms
      .filter((transform) => transform && typeof transform === "object")
      .map((transform) => ({
        id: typeof transform.id === "string" && transform.id ? transform.id : generateTransformId(),
        value: typeof transform.value === "string" ? transform.value : "",
      }))
      .filter((transform) => TRANSFORM_MAP[transform.value]);
  }

  if (
    condition.fieldRef &&
    typeof condition.fieldRef === "object" &&
    condition.fieldRef.type === "alias" &&
    typeof condition.fieldRef.transformId === "string"
  ) {
    normalized.fieldRef = {
      type: "alias",
      transformId: condition.fieldRef.transformId,
    };
  } else {
    normalized.fieldRef = null;
  }

  if (condition.query && typeof condition.query === "object") {
    normalized.query = hydrateGroup(condition.query);
  }

  return normalized;
}

function hydrateGroup(group) {
  const normalized = createGroup();
  if (!group || typeof group !== "object") {
    return normalized;
  }

  if (typeof group.id === "string" && group.id.trim()) {
    normalized.id = group.id;
  }
  normalized.logicalOperator = group.logicalOperator === "OR" ? "OR" : "AND";
  normalized.negated = Boolean(group.negated);
  if (Array.isArray(group.operators)) {
    normalized.operators = group.operators
      .map((value) => (value === "OR" ? "OR" : value === "AND" ? "AND" : null))
      .filter(Boolean);
  }

  if (Array.isArray(group.conditions)) {
    normalized.conditions = group.conditions.map(hydrateCondition);
  }
  if (Array.isArray(group.groups)) {
    normalized.groups = group.groups.map(hydrateGroup);
  }

  ensureGroupOperators(normalized);

  return normalized;
}

function replaceQueryState(newState) {
  queryState.id = newState.id;
  queryState.logicalOperator = newState.logicalOperator;
  queryState.operators = Array.isArray(newState.operators) ? [...newState.operators] : [];
  queryState.conditions = newState.conditions;
  queryState.groups = newState.groups;
  queryState.negated = newState.negated;
  latestDerivedTransformState = null;
}

function loadInitialQueryState() {
  if (!INITIAL_QUERY_PAYLOAD) {
    return;
  }

  try {
    const parsed = JSON.parse(INITIAL_QUERY_PAYLOAD);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return;
    }

    replaceQueryState(hydrateGroup(parsed));
  } catch (_error) {
    // Backward compatibility: ignore legacy non-JSON query payloads.
  }
}

function serializeCondition(condition) {
  const payload = {
    id: condition.id,
    field: condition.field || "",
    operator: condition.operator || "equals",
    value: condition.value ?? "",
    negated: Boolean(condition.negated),
    isVariableOnly: Boolean(condition.isVariableOnly),
  };

  if (Array.isArray(condition.transforms) && condition.transforms.length > 0) {
    payload.transforms = condition.transforms
      .filter((transform) => transform && typeof transform === "object")
      .map((transform) => ({
        id: typeof transform.id === "string" ? transform.id : generateTransformId(),
        value: transform.value,
      }))
      .filter((transform) => TRANSFORM_MAP[transform.value]);
  }

  if (
    condition.fieldRef &&
    typeof condition.fieldRef === "object" &&
    condition.fieldRef.type === "alias" &&
    typeof condition.fieldRef.transformId === "string"
  ) {
    payload.fieldRef = {
      type: "alias",
      transformId: condition.fieldRef.transformId,
    };
  }

  if (condition.query && typeof condition.query === "object") {
    payload.query = serializeGroup(condition.query);
  }

  return payload;
}

function serializeGroup(group) {
  const operators = ensureGroupOperators(group);
  return {
    id: group.id,
    logicalOperator: group.logicalOperator === "OR" ? "OR" : "AND",
    operators,
    negated: Boolean(group.negated),
    conditions: Array.isArray(group.conditions)
      ? group.conditions.map(serializeCondition)
      : [],
    groups: Array.isArray(group.groups) ? group.groups.map(serializeGroup) : [],
  };
}

function applyAdvancedQuery() {
  const payload = serializeGroup(queryState);
  const params = new URLSearchParams(window.location.search);
  params.set(ADVANCED_QUERY_PARAM, JSON.stringify(payload));
  params.delete("p");
  const search = params.toString();
  if (search) {
    window.location.search = `?${search}`;
    return;
  }
  window.location.href = window.location.pathname;
}

function clearAdvancedQuery() {
  const params = new URLSearchParams(window.location.search);
  if (!params.has(ADVANCED_QUERY_PARAM)) {
    return;
  }
  params.delete(ADVANCED_QUERY_PARAM);
  params.delete("p");
  const search = params.toString();
  if (search) {
    window.location.search = `?${search}`;
    return;
  }
  window.location.href = window.location.pathname;
}

function initializeAdminActions() {
  if (applyQueryButton) {
    applyQueryButton.addEventListener("click", applyAdvancedQuery);
  }
  if (clearQueryButton) {
    clearQueryButton.addEventListener("click", clearAdvancedQuery);
  }
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

  const allItems = getRenderableItems(group);
  ensureGroupOperators(group);

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
      const operatorValue = getGroupOperatorAt(group, idx);
      const operatorRow = document.createElement("div");
      operatorRow.className = "operator-row";

      const operatorButton = document.createElement("button");
      operatorButton.type = "button";
      operatorButton.className = "btn btn-outline btn-sm btn-operator";
      if (group.negated) {
        operatorButton.classList.add("negated");
      } else {
        operatorButton.classList.add(operatorValue === "AND" ? "and" : "or");
      }
      operatorButton.textContent = operatorValue;
      operatorButton.addEventListener("click", () => {
        setGroupOperatorAt(group, idx, operatorValue === "AND" ? "OR" : "AND");
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
  if (ENABLE_TRANSFORMS) {
    actions.appendChild(addSubqueryButton);
  }
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
  OPERATOR_OPTIONS.forEach((operator) => {
    const option = document.createElement("option");
    option.value = operator.value;
    option.textContent = operator.label;
    operatorSelect.appendChild(option);
  });
  operatorSelect.value = condition.operator;
  operatorSelect.addEventListener("change", (event) => {
    condition.operator = event.target.value;
    updatePreview();
  });
  row.appendChild(operatorSelect);

  const valueInput = document.createElement("input");
  valueInput.type = "text";
  valueInput.placeholder = "Value";
  valueInput.value = condition.value;
  valueInput.addEventListener("input", (event) => {
    condition.value = event.target.value;
    updatePreview();
  });
  row.appendChild(valueInput);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "btn btn-ghost btn-icon";
  removeButton.setAttribute("aria-label", "Remove condition");
  removeButton.appendChild(createIcon("trash"));
  removeButton.addEventListener("click", () => {
    parentGroup.conditions.splice(index, 1);
    renderApp();
  });
  row.appendChild(removeButton);

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
    const operatorLabel =
      OPERATOR_OPTIONS.find((option) => option.value === condition.operator)?.label || condition.operator;
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
      condition.operator === "in" || condition.operator === "not_in"
        ? `[${condition.value
            .split(",")
            .map((item) => item.trim())
            .filter((item) => item.length > 0)
            .join(", ")}]`
        : `"${condition.value}"`;
    const prefix = condition.negated ? "NOT " : "";
    const line = `${"  ".repeat(indent + 1)}${prefix}${fieldLabel} ${operatorLabel} ${valueLabel}`;
    items.push(line);
  });

  group.groups.forEach((nestedGroup) => {
    items.push(generateQueryString(nestedGroup, indent + 1, false));
  });

  if (items.length > 0) {
    result += items[0];
    for (let index = 1; index < items.length; index += 1) {
      const operator = getGroupOperatorAt(group, index - 1);
      result += `\n${"  ".repeat(indent + 1)}${operator}\n${items[index]}`;
    }
  }

  if (!isRoot || group.negated) {
    result += `\n${indentation})`;
  }

  return result;
}

function generateDjangoORM(group) {
  const operatorMap = {
    equals: "",
    not_equals: "",
    contains: "__contains",
    not_contains: "__contains",
    greater_than: "__gt",
    less_than: "__lt",
    in: "__in",
    not_in: "__in",
  };

  const annotations = new Map();
  const aggregations = new Map();
  const imports = new Set();
  const derived = getDerivedTransformState();

  const escapeValue = (value) => value.replace(/\\/g, "\\\\").replace(/'/g, "\\'");

  const formatBoolean = (value) => (value.toLowerCase() === "true" ? "True" : "False");

  const formatScalarValue = (raw) => {
    const trimmed = raw.trim();
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
    const parts = raw
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
      .map((item) => formatScalarValue(item));

    return `[${parts.join(", ")}]`;
  };

  const formatValue = (value, operator) => {
    if (operator === "in" || operator === "not_in") {
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
      const suffix = operatorMap[condition.operator] || "";
      let isNegated = condition.negated || condition.operator.startsWith("not_");

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

      let valueExpression;
      if (condition.operator === "in" || condition.operator === "not_in") {
        valueExpression = formatValue(condition.value, condition.operator);
      } else {
        valueExpression = formatValue(condition.value, condition.operator);
      }

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

    let combined = parts[0];
    for (let index = 1; index < parts.length; index += 1) {
      const operator = getGroupOperatorAt(g, index - 1);
      const joiner = operator === "OR" ? " | " : " & ";
      combined = `${combined}${joiner}${parts[index]}`;
    }

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
    BUILDER_CONFIG,
    serializeGroup,
    hydrateGroup,
    loadInitialQueryState,
    applyAdvancedQuery,
    clearAdvancedQuery,
    OPERATOR_OPTIONS,
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
    queryState,
    makeAlias,
    toDjangoPath,
  };
}

loadInitialQueryState();
initializeAdminActions();
initializePreviewToggle();
renderApp();
