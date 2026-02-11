import { describe, it, expect, beforeEach, vi } from "vitest";
import { JSDOM } from "jsdom";

let builder;

const createDom = () => {
  const dom = new JSDOM(`<!DOCTYPE html><body><div id="query-root"></div><pre id="readable-preview"></pre><pre id="django-preview"></pre><div id="preview-wrapper" class="preview-wrapper is-hidden"></div><button id="preview-toggle"></button></body>`);
  global.window = dom.window;
  global.document = dom.window.document;
  global.SVGElement = dom.window.SVGElement;
  global.HTMLElement = dom.window.HTMLElement;
  global.Node = dom.window.Node;
  global.CustomEvent = dom.window.CustomEvent;
  window.alert = vi.fn();
};

const loadBuilder = async () => {
  vi.resetModules();
  const module = await import("../main.js");
  builder = module.default || module;
};

const resetQueryState = () => {
  builder.queryState.conditions = [];
  builder.queryState.groups = [];
  builder.queryState.logicalOperator = "AND";
  builder.queryState.negated = false;
};

beforeEach(async () => {
  createDom();
  await loadBuilder();
  resetQueryState();
});

describe("automatic transform behavior", () => {
  it("treats transforms as aggregations when unused outside and exposes .aggregate output", () => {
    const childGroup = builder.createGroup();
    const childCondition = builder.createCondition();
    childCondition.field = "order.total";
    childCondition.operator = "equals";
    childCondition.value = "5";
    childCondition.transforms = [{ value: "count" }];
    builder.normalizeConditionTransforms(childCondition);
    childGroup.conditions.push(childCondition);
    builder.queryState.groups.push(childGroup);

    builder.rebuildDerivedTransformState();
    const derived = builder.getDerivedTransformState();
    const transformMeta = derived.transformsById.get(childCondition.transforms[0].id);
    expect(transformMeta.behavior).toBe("aggregation");

    const django = builder.generateDjangoORM(builder.queryState);
    expect(django).toContain("result = queryset.aggregate");
    expect(django).toContain("Count(");
  });

  it("promotes transforms to annotations when referenced by ancestor groups", () => {
    const childGroup = builder.createGroup();
    const childCondition = builder.createCondition();
    childCondition.field = "order.total";
    childCondition.operator = "equals";
    childCondition.value = "5";
    childCondition.transforms = [{ value: "count" }];
    builder.normalizeConditionTransforms(childCondition);
    childGroup.conditions.push(childCondition);
    builder.queryState.groups.push(childGroup);

    builder.rebuildDerivedTransformState();
    let derived = builder.getDerivedTransformState();
    const childMeta = derived.transformsById.get(childCondition.transforms[0].id);

    const parentCondition = builder.createCondition();
    parentCondition.field = childMeta.alias;
    parentCondition.fieldRef = { type: "alias", transformId: childMeta.id };
    parentCondition.operator = "greater_than";
    parentCondition.value = "2";
    builder.queryState.conditions.push(parentCondition);

    builder.rebuildDerivedTransformState();
    derived = builder.getDerivedTransformState();
    const updatedMeta = derived.transformsById.get(childMeta.id);
    expect(updatedMeta.behavior).toBe("annotation");

    const django = builder.generateDjangoORM(builder.queryState);
    expect(django).toContain(".annotate(");
    expect(django).toContain(`${updatedMeta.alias}=`);
    expect(django).toContain(`.filter(Q(${updatedMeta.alias}`);
    expect(django).not.toContain("result = queryset.aggregate");
  });

  it("exposes generated aliases to ancestor groups via field options", () => {
    const childGroup = builder.createGroup();
    const childCondition = builder.createCondition();
    childCondition.field = "order.total";
    childCondition.transforms = [{ value: "sum" }];
    builder.normalizeConditionTransforms(childCondition);
    childGroup.conditions.push(childCondition);
    builder.queryState.groups.push(childGroup);

    builder.rebuildDerivedTransformState();
    const derived = builder.getDerivedTransformState();
    const transformMeta = derived.transformsById.get(childCondition.transforms[0].id);
    const fieldOptions = builder.getFieldOptionsForGroup(builder.queryState.id);
    expect(
      fieldOptions.some((option) => option.value === transformMeta.alias && option.type === "alias")
    ).toBe(true);
  });

  it("generates deterministic aliases without random suffixes", () => {
    const childGroup = builder.createGroup();
    const childCondition = builder.createCondition();
    childCondition.field = "user.email";
    childCondition.transforms = [{ value: "count" }];
    builder.normalizeConditionTransforms(childCondition);
    childGroup.conditions.push(childCondition);
    builder.queryState.groups.push(childGroup);

    builder.rebuildDerivedTransformState();
    const derived = builder.getDerivedTransformState();
    const alias = derived.transformsById.get(childCondition.transforms[0].id).alias;
    expect(alias).toBe("count_user_email");
  });

  it("marks aggregation-only transforms in the readable preview", () => {
    const childGroup = builder.createGroup();
    const childCondition = builder.createCondition();
    childCondition.field = "order.total";
    childCondition.operator = "greater_than";
    childCondition.value = "10";
    childCondition.transforms = [{ value: "sum" }];
    builder.normalizeConditionTransforms(childCondition);
    childGroup.conditions.push(childCondition);
    builder.queryState.groups.push(childGroup);

    builder.rebuildDerivedTransformState();
    const readable = builder.generateQueryString(builder.queryState, 0, true);
    expect(readable).toContain("Aggregation:");
    expect(readable).toContain("SUM(");
  });
});

describe("subquery controls", () => {
  it("allows adding multiple subqueries within the same group", () => {
    builder.queryState.conditions = [];
    builder.queryState.groups = [];
    builder.renderApp?.();

    const getAddSubqueryButton = () => {
      const buttons = Array.from(document.querySelectorAll(".group-actions button"));
      return buttons.find((btn) => btn.textContent.includes("Add Subquery"));
    };

    const first = getAddSubqueryButton();
    expect(first).toBeTruthy();
    first.click();

    const second = getAddSubqueryButton();
    expect(second).toBeTruthy();
    second.click();

    expect(builder.queryState.conditions.filter((c) => c.isVariableOnly).length).toBe(2);
  });
});
