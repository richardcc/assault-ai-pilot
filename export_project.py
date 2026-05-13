import os

def export_folder_to_txt(folder_path, output_file):
    with open(output_file, "w", encoding="utf-8") as outfile:
        for root, dirs, files in os.walk(folder_path):
            
            # Ignorar carpetas basura
            dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".venv", "node_modules"]]

            for file in files:
                file_path = os.path.join(root, file)

                # Ignorar archivos binarios o pesados
                if file.endswith((".pyc", ".exe", ".dll", ".png", ".jpg", ".jpeg", ".zip")):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        outfile.write(f"\n{'='*80}\n")
                        outfile.write(f"FILE: {file_path}\n")
                        outfile.write(f"{'='*80}\n\n")

                        outfile.write(infile.read())
                        outfile.write("\n\n")

                except Exception as e:
                    outfile.write(f"\nERROR leyendo {file_path}: {e}\n\n")


if __name__ == "__main__":
    base_path = r"C:\repos\python\assault"

    print("📁 Proyectos disponibles:\n")

    folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]

    for i, folder in enumerate(folders):
        print(f"{i} -> {folder}")

    choice = int(input("\nSelecciona el proyecto (número): "))
    selected_folder = folders[choice]

    project_path = os.path.join(base_path, selected_folder)
    output_file = os.path.join(base_path, f"{selected_folder}_export.txt")

    export_folder_to_txt(project_path, output_file)

    print(f"\n✅ Exportado: {output_file}")