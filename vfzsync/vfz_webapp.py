# Entry point for the application.
from vfzsync import app    # For application discovery by the 'flask' command. 
import vfz_routes  # For import side-effects of setting up routes. 

if __name__ == "__main__":
    app.run(host='0.0.0.0')
