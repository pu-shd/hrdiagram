declare module "*.mjs" {
  export function loadPyodide(options: {indexURL: string}): Promise<any>;
}
