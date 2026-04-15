#!/usr/bin/env python3
"""
Seed script to insert sample employees into the MySQL database.
"""

import json
from app.database import bulk_create_employees, create_job, initialize_database

# Sample employee data (camelCase to snake_case mapping)
employees_data = [
    {
        "id": "E001",
        "job_number": "J001",
        "full_name": "Alice Johnson",
        "team": "Engineering",
        "location": "London",
        "avatar_url": "https://example.com/avatars/alice.jpg",
        "status": "active",
        "service": "Platform Development",
        "grade": "Senior",
        "appraisal_due_date": "2026-09-15"
    },
    {
        "id": "E002",
        "job_number": "J002",
        "full_name": "Brian Smith",
        "team": "Data",
        "location": "Manchester",
        "avatar_url": "https://example.com/avatars/brian.jpg",
        "status": "active",
        "service": "Business Intelligence",
        "grade": "Mid",
        "appraisal_due_date": "2026-07-20"
    },
    {
        "id": "E003",
        "job_number": "J003",
        "full_name": "Clara Evans",
        "team": "Operations",
        "location": "Birmingham",
        "avatar_url": "https://example.com/avatars/clara.jpg",
        "status": "active",
        "service": "Project Delivery",
        "grade": "Senior",
        "appraisal_due_date": "2026-11-05"
    },
    {
        "id": "E004",
        "job_number": "J004",
        "full_name": "David Brown",
        "team": "Marketing",
        "location": "Leeds",
        "avatar_url": "https://example.com/avatars/david.jpg",
        "status": "active",
        "service": "Digital Marketing",
        "grade": "Mid",
        "appraisal_due_date": "2026-08-12"
    },
    {
        "id": "E005",
        "job_number": "J005",
        "full_name": "Ella Wilson",
        "team": "Design",
        "location": "London",
        "avatar_url": "https://example.com/avatars/ella.jpg",
        "status": "active",
        "service": "User Experience",
        "grade": "Senior",
        "appraisal_due_date": "2026-10-01"
    },
    {
        "id": "E006",
        "job_number": "J006",
        "full_name": "Frank Taylor",
        "team": "Sales",
        "location": "Glasgow",
        "avatar_url": "https://example.com/avatars/frank.jpg",
        "status": "active",
        "service": "Enterprise Sales",
        "grade": "Mid",
        "appraisal_due_date": "2026-06-30"
    },
    {
        "id": "E007",
        "job_number": "J007",
        "full_name": "Grace Hall",
        "team": "HR",
        "location": "Bristol",
        "avatar_url": "https://example.com/avatars/grace.jpg",
        "status": "active",
        "service": "People Operations",
        "grade": "Senior",
        "appraisal_due_date": "2026-12-10"
    },
    {
        "id": "E008",
        "job_number": "J008",
        "full_name": "Henry Clark",
        "team": "Finance",
        "location": "Edinburgh",
        "avatar_url": "https://example.com/avatars/henry.jpg",
        "status": "active",
        "service": "Financial Planning",
        "grade": "Mid",
        "appraisal_due_date": "2026-09-25"
    },
    {
        "id": "E009",
        "job_number": "J009",
        "full_name": "Isla Turner",
        "team": "Support",
        "location": "Liverpool",
        "avatar_url": "https://example.com/avatars/isla.jpg",
        "status": "active",
        "service": "Customer Support",
        "grade": "Junior",
        "appraisal_due_date": "2026-05-18"
    },
    {
        "id": "E010",
        "job_number": "J010",
        "full_name": "Jack Walker",
        "team": "Engineering",
        "location": "London",
        "avatar_url": "https://example.com/avatars/jack.jpg",
        "status": "active",
        "service": "Infrastructure",
        "grade": "Senior",
        "appraisal_due_date": "2026-11-22"
    }
]

if __name__ == "__main__":
    # Initialize database (create tables if not exist)
    initialize_database()

    # Create unique jobs
    job_numbers = set(emp["job_number"] for emp in employees_data)
    for job_num in job_numbers:
        try:
            create_job({"job_number": job_num, "job_title": f"Job {job_num}"})
        except Exception as e:
            print(f"Job {job_num} might already exist: {e}")

    # Insert employees
    created, errors = bulk_create_employees(employees_data)

    print(f"Created {len(created)} employees.")
    if errors:
        print(f"Errors: {errors}")