clear
set -e
echo ""
echo "###################################################################"
echo "[[[  Running: git fetch --all on current working directory: ]]]"
echo "$PWD"
git fetch --all
echo "###################################################################" && sleep 2
echo ""
echo ""
echo "###################################################################"
echo "[[[  Running git checkout on $1  ]]]"
git checkout $1
echo "###################################################################" && sleep 2
echo ""
echo ""
echo "###################################################################"
echo "[[[  Git status O/P: ]]]"
Git_Status=$(git status | head -n 5)
echo "$Git_Status"
echo "###################################################################" && sleep 2
echo ""
echo ""
read -p "Do you want to proceed? (yes/no) " User_Input
case $User_Input in
yes)
  echo Proceeding with deployment
  export GIT_COMMIT_SHA=$(git rev-parse --short HEAD)
  export GIT_REF=$(git describe --tags --exact-match 2>/dev/null || git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD)
  copilot svc deploy --name rm-fastapi-agent --env prod
  echo "Completed"
  break
  ;;
no)
  echo Exiting...
  exit
  ;;
*) echo Invalid input ;;
esac
