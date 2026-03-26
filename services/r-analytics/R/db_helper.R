#' Database Connection Helper
#' @import DBI RPostgres
get_db_conn <- function() {
  conf <- config::get()$db
  
  con <- dbConnect(
    RPostgres::Postgres(),
    host = conf$host,
    port = conf$port,
    dbname = conf$dbname,
    user = conf$user,
    password = conf$password
  )
  
  return(con)
}

#' Safe query helper for typed tibbles
#' @import tibble DBI
safe_query <- function(con, query, params = NULL, empty_types = NULL) {
  res <- tryCatch({
    if (is.null(params)) {
      dbGetQuery(con, query)
    } else {
      dbGetQuery(con, query, params = params)
    }
  }, error = function(e) {
    message("Query failed: ", e$message)
    return(NULL)
  })
  
  if (is.null(res) || nrow(res) == 0) {
    if (!is.null(empty_types)) {
      return(as_tibble(empty_types))
    }
    return(as_tibble(data.frame()))
  }
  
  return(as_tibble(res))
}
