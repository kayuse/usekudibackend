

from fastapi.params import Depends


async def get_profile(request, db: Session = Depends(get_db)):
    
    profile = await request.profile_service.get_profile(request.user.id, db)
    
    return HttpResponse(
        content=profile,
        status_code=status.HTTP_200_OK,
        media_type="application/json"
    )