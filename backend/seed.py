import os
import re
import shutil
from pathlib import Path
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, SessionLocal, Base
from app.models import User, Role, Permission, Document
from app.auth import get_password_hash
from app.rag import index_document_content

def parse_txt_reports(file_path: Path) -> list[dict]:
    """
    Parses a single file containing multiple reports separated by dividers.
    Extracts report title, company, type, and content block.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    blocks = re.split(r'={40,}', content)
    reports = []

    company_name = "NMap InfoTech"
    for line in content.split("\n")[:10]:
        if "COMPANY_NAME:" in line:
            company_name = line.split("COMPANY_NAME:")[1].strip()
        elif "COMPANY VALUATION:" in line:
            pass
            
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        match = re.search(r'REPORT \d+:\s*(.+)', block)
        if not match:
            continue
            
        lines = block.split("\n")
        title = match.group(1).strip().replace("=", "").strip()
        
        report_id = f"{file_path.stem.lower().replace('_', '-')}-gen-{len(reports) + 1}"
        doc_type = "report"
        
        for line in lines:
            line_clean = line.strip()
            if line_clean.startswith("REPORT_ID:"):
                report_id = line_clean.split("REPORT_ID:")[1].strip()
            elif line_clean.startswith("REPORT_TYPE:"):
                type_val = line_clean.split("REPORT_TYPE:")[1].strip().lower()
                if "invoice" in type_val:
                    doc_type = "invoice"
                elif "contract" in type_val or "agreement" in type_val:
                    doc_type = "contract"
                else:
                    doc_type = "report"
            elif line_clean.startswith("COMPANY_NAME:"):
                company_name = line_clean.split("COMPANY_NAME:")[1].strip()

        cleaned_lines = [l for l in lines if not re.match(r'^[=\-_*#]+$', l.strip())]
        report_content = "\n".join(cleaned_lines).strip()
        
        reports.append({
            "report_id": report_id,
            "title": f"{report_id}: {title}",
            "company_name": company_name,
            "document_type": doc_type,
            "content": report_content
        })
        
    return reports

def main():
    print("Initializing Database tables...")
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        print("Ensuring standard Roles and Permissions are seeded...")
        perms_dict = {
            "full_access": "Full administrator system access",
            "upload_document": "Ability to upload new financial documents",
            "edit_document": "Ability to edit document properties",
            "review_document": "Ability to review and audit documents",
            "view_document": "Ability to view and search documents"
        }
        for name, desc in perms_dict.items():
            if not db.query(Permission).filter(Permission.name == name).first():
                db.add(Permission(name=name, description=desc))
        db.commit()

        roles_dict = {
            "Admin": "System Administrator with unrestricted access",
            "Financial Analyst": "Analyst role for document operations",
            "Auditor": "Auditor role for document review and validation",
            "Client": "External client with access strictly bounded by company profile"
        }
        for name, desc in roles_dict.items():
            if not db.query(Role).filter(Role.name == name).first():
                db.add(Role(name=name, description=desc))
        db.commit()
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        analyst_role = db.query(Role).filter(Role.name == "Financial Analyst").first()
        auditor_role = db.query(Role).filter(Role.name == "Auditor").first()
        client_role = db.query(Role).filter(Role.name == "Client").first()

        full_access_p = db.query(Permission).filter(Permission.name == "full_access").first()
        upload_p = db.query(Permission).filter(Permission.name == "upload_document").first()
        edit_p = db.query(Permission).filter(Permission.name == "edit_document").first()
        review_p = db.query(Permission).filter(Permission.name == "review_document").first()
        view_p = db.query(Permission).filter(Permission.name == "view_document").first()

        if admin_role and not admin_role.permissions:
            admin_role.permissions.append(full_access_p)
        if analyst_role and not analyst_role.permissions:
            analyst_role.permissions.extend([upload_p, edit_p, view_p])
        if auditor_role and not auditor_role.permissions:
            auditor_role.permissions.extend([review_p, view_p])
        if client_role and not client_role.permissions:
            client_role.permissions.append(view_p)
        db.commit()

        print("Checking default test users...")
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@nmapinfotech.com",
                hashed_password=get_password_hash("adminpassword"),
                company_name="NMap InfoTech"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            admin_user.roles.append(admin_role)
            db.commit()
            print("Created default user: admin / adminpassword")

        client_user = db.query(User).filter(User.username == "client").first()
        if not client_user:
            client_user = User(
                username="client",
                email="client@nmapinfotech.com",
                hashed_password=get_password_hash("clientpassword"),
                company_name="NMap InfoTech"
            )
            db.add(client_user)
            db.commit()
            db.refresh(client_user)
            client_user.roles.append(client_role)
            db.commit()
            print("Created default user: client / clientpassword")

        data_dir = Path(__file__).resolve().parent / "data"
        if not data_dir.exists():
            data_dir = Path(__file__).resolve().parent.parent / "data"

        print(f"Scanning data folder: {data_dir}")
        if not data_dir.exists():
            print(f"Error: Data directory not found at {data_dir}")
            return

        txt_files = list(data_dir.glob("*.txt"))
        print(f"Found {len(txt_files)} report files to process.")

        total_ingested = 0
        for file_path in txt_files:
            print(f"Parsing: {file_path.name}")
            parsed_reports = parse_txt_reports(file_path)
            print(f"Found {len(parsed_reports)} sub-reports inside {file_path.name}")
            
            for report in parsed_reports:
                existing_doc = db.query(Document).filter(Document.title == report["title"]).first()
                if existing_doc:
                    continue
 
                doc_id = report["report_id"]
                file_name = f"{doc_id}_seeded.txt"
                dest_path = settings.UPLOAD_DIR / file_name
                
                with open(dest_path, "w", encoding="utf-8") as f_out:
                    f_out.write(report["content"])
                
                new_doc = Document(
                    id=doc_id,
                    title=report["title"],
                    company_name=report["company_name"],
                    document_type=report["document_type"],
                    filepath=str(dest_path),
                    uploaded_by=admin_user.id
                )
                db.add(new_doc)
                db.commit()
                db.refresh(new_doc)
                
                try:
                    metadata = {
                        "title": report["title"],
                        "company_name": report["company_name"],
                        "document_type": report["document_type"]
                    }
                    chunks_indexed = index_document_content(doc_id, report["content"], metadata)
                    print(f"  -> Ingested {doc_id} successfully ({chunks_indexed} vectors generated)")
                    total_ingested += 1
                except Exception as e:
                    print(f"  -> Error vectorizing {doc_id}: {e}")

        print(f"Ingestion process finished. Total parsed documents ingested: {total_ingested}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
