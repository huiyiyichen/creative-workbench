from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectArtifact, ProjectRevision, ProjectUpload


class StudioRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, project_id: int, owner_id: int, *, lock: bool = False):
        query = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self.db.execute(query)).scalar_one_or_none()

    async def list(self, owner_id: int):
        query = select(Project).where(Project.owner_id == owner_id)
        return (await self.db.execute(query.order_by(Project.updated_at.desc()).limit(100))).scalars().all()

    async def create(self, owner_id: int, spec: dict, source: dict):
        project = Project(owner_id=owner_id, title=spec["brief"]["theme"], spec=spec, source_snapshot=source)
        self.db.add(project)
        await self.db.flush()
        await self.snapshot(project, "created")
        return project

    async def snapshot(self, project: Project, reason: str):
        self.db.add(
            ProjectRevision(
                project_id=project.id,
                version=project.version,
                spec=deepcopy(project.spec),
                reason=reason,
            )
        )
        await self.db.flush()

    async def revisions(self, project_id: int):
        query = select(ProjectRevision).where(ProjectRevision.project_id == project_id)
        return (await self.db.execute(query.order_by(ProjectRevision.version.desc()).limit(100))).scalars().all()

    async def revision(self, project_id: int, version: int):
        query = select(ProjectRevision).where(
            ProjectRevision.project_id == project_id,
            ProjectRevision.version == version,
        )
        return (await self.db.execute(query)).scalar_one_or_none()

    async def assets(self, project_id: int):
        query = select(ProjectUpload).where(ProjectUpload.project_id == project_id).order_by(ProjectUpload.id)
        return (await self.db.execute(query)).scalars().all()

    async def asset(self, project_id: int, asset_id: int):
        query = select(ProjectUpload).where(ProjectUpload.project_id == project_id, ProjectUpload.id == asset_id)
        return (await self.db.execute(query)).scalar_one_or_none()

    async def add_asset(self, **values):
        asset = ProjectUpload(**values)
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def artifacts(self, project_id: int):
        query = select(ProjectArtifact).where(ProjectArtifact.project_id == project_id)
        return (await self.db.execute(query.order_by(ProjectArtifact.id.desc()))).scalars().all()

    async def artifact(self, artifact_id: int):
        return await self.db.get(ProjectArtifact, artifact_id)

    async def add_artifact(self, project_id: int, version: int, kind: str):
        artifact = ProjectArtifact(project_id=project_id, version=version, kind=kind)
        self.db.add(artifact)
        await self.db.flush()
        return artifact

    async def unfinished(self):
        query = select(ProjectArtifact).where(ProjectArtifact.status.in_(["queued", "rendering"]))
        return (await self.db.execute(query)).scalars().all()

    async def jobs(self, owner_id: int):
        query = (
            select(ProjectArtifact, Project.title)
            .join(Project, Project.id == ProjectArtifact.project_id)
            .where(Project.owner_id == owner_id)
            .order_by(ProjectArtifact.id.desc())
            .limit(30)
        )
        return (await self.db.execute(query)).all()
