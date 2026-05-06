import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDatastacks, useTours } from "../api/queries";
import { useUrlParam } from "../hooks/useUrlState";
import type { Example, Recipe } from "../api/types";
import { buildExampleParams, buildRecipeOpenParams } from "../tours/urlMint";
import { useApplyRecipe } from "../tours/useApplyRecipe";
import {
  listForDs as listPersonalRecipes,
  remove as removePersonalRecipe,
  save as savePersonalRecipe,
  subscribe as subscribePersonalRecipes,
} from "../tours/personalRecipes";
import { parseRecipesFromYaml } from "../tours/recipeFromYaml";
import { recipeToYaml } from "../tours/recipeYaml";

/**
 * Operator-curated landing page. Replaces the bare `<Navigate to="/neuron" />`
 * index route. Shows tours grouped by datastack — Examples open a fully-
 * configured workspace; Recipes overlay configuration onto the user's
 * currently-loaded cell.
 *
 * Datastacks are shown in the order the backend returned them (which is
 * the operator-controlled `DATASTACKS_ALLOWED` list). Empty datastacks
 * (no examples + no recipes) render a brief empty-state instead of
 * being hidden — they're still selectable via the sidebar.
 */
export function LandingPage() {
  const datastacks = useDatastacks();
  const list = datastacks.data?.datastacks ?? [];

  return (
    <div className="landing">
      <header className="landing-header">
        <h2>CAVE Data Viewer</h2>
        <p>
          Apply a recipe to overlay decorations and plots onto a cell you're
          already exploring, or open a curated example to land on a fully
          configured workspace.
        </p>
      </header>
      {datastacks.isLoading && <p>Loading datastacks…</p>}
      {datastacks.isError && (
        <p className="error">
          Failed to load datastacks:{" "}
          {datastacks.error instanceof Error ? datastacks.error.message : "unknown"}
        </p>
      )}
      {list.map((ds) => (
        <DatastackTours key={ds} ds={ds} />
      ))}
    </div>
  );
}

function DatastackTours({ ds }: { ds: string }) {
  const tours = useTours(ds);
  const data = tours.data;
  // Subscribe to personal-recipe mutations so the section re-renders when
  // a YAML upload finishes or the user deletes one.
  const [, setPersonalTick] = useState(0);
  useEffect(() => subscribePersonalRecipes(() => setPersonalTick((n) => n + 1)), []);
  const personalRecipes = listPersonalRecipes(ds);

  const operatorRecipes = data?.recipes ?? [];
  const examples = data?.examples ?? [];
  const empty =
    data && examples.length === 0 && operatorRecipes.length === 0 && personalRecipes.length === 0;

  return (
    <section className="landing-datastack">
      <h3>{ds}</h3>
      {tours.isLoading && <p className="muted">Loading examples and recipes…</p>}
      {tours.isError && (
        <p className="error">
          Failed to load examples and recipes:{" "}
          {tours.error instanceof Error ? tours.error.message : "unknown"}
        </p>
      )}
      {empty && (
        <p className="muted">
          No examples or recipes configured for this datastack — load one from a
          YAML file below, or pick this datastack in the sidebar to start fresh.
        </p>
      )}
      {(operatorRecipes.length > 0 || personalRecipes.length > 0) && (
        <div className="tour-section">
          <h4>Recipes</h4>
          {personalRecipes.length > 0 && (
            <>
              <h5 className="tour-subgroup">My recipes</h5>
              <div className="tour-grid">
                {personalRecipes.map((r) => (
                  <RecipeCard key={r.id} ds={ds} recipe={r} personal />
                ))}
              </div>
            </>
          )}
          {operatorRecipes.length > 0 && (
            <>
              {personalRecipes.length > 0 && (
                <h5 className="tour-subgroup">Operator recipes</h5>
              )}
              <div className="tour-grid">
                {operatorRecipes.map((r) => (
                  <RecipeCard key={r.id} ds={ds} recipe={r} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
      {examples.length > 0 && (
        <div className="tour-section">
          <h4>Examples</h4>
          <div className="tour-grid">
            {examples.map((ex) => (
              <ExampleCard key={ex.id} ds={ds} example={ex} />
            ))}
          </div>
        </div>
      )}
      <RecipeYamlUploader ds={ds} />
    </section>
  );
}

/**
 * "Load recipe from YAML" affordance scoped to one datastack. Accepts
 * either a file picker or text paste; the parsed recipes are stored as
 * personal recipes for THIS datastack only (recipes are inherently
 * datastack-specific because their decoration tables and column names
 * reference datastack-bound CAVE state).
 *
 * Errors from `parseRecipesFromYaml` are surfaced inline; warnings (per-
 * field salvage notes) appear collapsed under a "Show details" toggle so
 * a successful-but-noisy upload doesn't drown the success message.
 */
function RecipeYamlUploader({ ds }: { ds: string }) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [result, setResult] = useState<{
    ok: number;
    warnings: string[];
    errors: string[];
  } | null>(null);

  const handleYaml = (yamlText: string, source: string) => {
    const parsed = parseRecipesFromYaml(yamlText);
    for (const recipe of parsed.recipes) savePersonalRecipe(ds, recipe);
    setResult({
      ok: parsed.recipes.length,
      warnings: parsed.warnings,
      errors: parsed.errors.length > 0 ? parsed.errors : parsed.recipes.length === 0 ? [`No recipes loaded from ${source}.`] : [],
    });
  };

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    handleYaml(text, file.name);
    // Reset so re-uploading the same file re-triggers the change event.
    e.target.value = "";
  };

  const onPasteSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pasteText.trim()) return;
    handleYaml(pasteText, "pasted YAML");
    setPasteText("");
    setPasteOpen(false);
  };

  return (
    <div className="recipe-uploader">
      <h4>Load recipe from YAML</h4>
      <p className="muted">
        Paste a recipe YAML or upload a file (e.g. one downloaded from the
        sidebar). Loaded recipes go into <em>your personal recipes</em> for
        this datastack only.
      </p>
      <div className="recipe-uploader-actions">
        <button type="button" onClick={() => fileInputRef.current?.click()}>
          Choose file…
        </button>
        <button type="button" onClick={() => setPasteOpen((s) => !s)}>
          {pasteOpen ? "Cancel paste" : "Paste YAML"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".yaml,.yml,.txt,application/x-yaml,text/yaml,text/plain"
          onChange={onFileChosen}
          style={{ display: "none" }}
        />
      </div>
      {pasteOpen && (
        <form className="recipe-uploader-paste" onSubmit={onPasteSubmit}>
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={10}
            placeholder={`recipes:\n  - id: my-recipe\n    title: ...`}
            autoFocus
          />
          <button type="submit" disabled={!pasteText.trim()}>
            Load
          </button>
        </form>
      )}
      {result && <RecipeUploadResult result={result} onDismiss={() => setResult(null)} />}
    </div>
  );
}

function RecipeUploadResult({
  result,
  onDismiss,
}: {
  result: { ok: number; warnings: string[]; errors: string[] };
  onDismiss: () => void;
}) {
  const hasError = result.errors.length > 0;
  const hasWarn = result.warnings.length > 0;
  return (
    <div className={`recipe-uploader-result ${hasError ? "is-error" : "is-success"}`}>
      <div className="recipe-uploader-result-header">
        {result.ok > 0 && (
          <span>
            ✓ Loaded {result.ok} recipe{result.ok === 1 ? "" : "s"}.
          </span>
        )}
        {hasError && <span>✗ {result.errors.length} error{result.errors.length === 1 ? "" : "s"}.</span>}
        <button type="button" className="link-button" onClick={onDismiss}>
          dismiss
        </button>
      </div>
      {hasError && (
        <ul>
          {result.errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {hasWarn && (
        <details>
          <summary>{result.warnings.length} warning{result.warnings.length === 1 ? "" : "s"}</summary>
          <ul>
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function summarizeTour(t: Example | Recipe): string {
  const parts: string[] = [];
  if (t.decoration_tables.length > 0) {
    parts.push(
      `${t.decoration_tables.length} decoration${t.decoration_tables.length === 1 ? "" : "s"}`,
    );
  }
  if (t.plots.length > 0) {
    parts.push(`${t.plots.length} plot${t.plots.length === 1 ? "" : "s"}`);
  }
  if (t.cells) parts.push("cell filter");
  return parts.join(" · ");
}

function ExampleCard({ ds, example }: { ds: string; example: Example }) {
  const navigate = useNavigate();
  const open = () => {
    const params = buildExampleParams(ds, example);
    navigate(`/neuron?${params.toString()}`);
  };
  return (
    <div className="tour-card">
      <h5>{example.title}</h5>
      {example.description && <p className="tour-desc">{example.description}</p>}
      <p className="tour-meta">
        v{example.mat_version} · root {example.root.slice(0, 6)}…{example.root.slice(-4)}
        {summarizeTour(example) && <> · {summarizeTour(example)}</>}
      </p>
      <button type="button" className="tour-cta" onClick={open}>
        Open
      </button>
    </div>
  );
}

function RecipeCard({ ds, recipe, personal }: { ds: string; recipe: Recipe; personal?: boolean }) {
  const navigate = useNavigate();
  const [currentDs] = useUrlParam("ds");
  const [currentMv] = useUrlParam("mv");
  const [currentRoot] = useUrlParam("root");
  const applyRecipe = useApplyRecipe();
  // Apply overlays the recipe onto a loaded cell — requires same ds + a root.
  // Open preconfigures the workspace and lands on /neuron with no root, so
  // the user fills it in. Mutually exclusive in the UI to avoid two CTAs
  // racing for the same click; Apply is preferred when available because
  // it's the more common workflow (user already exploring a cell, wants to
  // try a different lens on it).
  const sameDs = currentDs === ds;
  const canApply = sameDs && !!currentRoot;
  const open = () => {
    // mv preserved from the sidebar only when the user is already on this
    // datastack — switching to a different datastack's recipe should land
    // the user without a stale mat_version that doesn't apply to the new ds.
    const mvToCarry = sameDs ? currentMv : null;
    const params = buildRecipeOpenParams(ds, recipe, mvToCarry);
    navigate(`/neuron?${params.toString()}`);
  };
  const onDownload = () => {
    const yaml = recipeToYaml(recipe);
    const blob = new Blob([yaml], { type: "application/x-yaml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const slug = recipe.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    a.download = `${slug || recipe.id}.recipe.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  const onDelete = () => {
    if (!window.confirm(`Delete personal recipe "${recipe.title}"?`)) return;
    removePersonalRecipe(ds, recipe.id);
  };
  return (
    <div className={`tour-card${personal ? " is-personal" : ""}`}>
      <h5>{recipe.title}</h5>
      {recipe.description && <p className="tour-desc">{recipe.description}</p>}
      {summarizeTour(recipe) && <p className="tour-meta">{summarizeTour(recipe)}</p>}
      <div className="tour-card-actions">
        {canApply ? (
          <button
            type="button"
            className="tour-cta"
            onClick={() => applyRecipe(recipe)}
            title={`Overlay onto cell ${currentRoot.slice(0, 6)}…${currentRoot.slice(-4)}`}
          >
            Apply
          </button>
        ) : (
          <button
            type="button"
            className="tour-cta"
            onClick={open}
            title="Open the workspace preconfigured with this recipe — pick a cell once you're there"
          >
            Open
          </button>
        )}
        {personal && (
          <>
            <button type="button" className="tour-secondary" onClick={onDownload} title="Download as YAML">
              YAML
            </button>
            <button type="button" className="tour-secondary" onClick={onDelete} title="Delete this personal recipe">
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}
